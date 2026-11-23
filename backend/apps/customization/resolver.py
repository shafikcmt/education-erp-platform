"""Effective configuration (Phase 5 M1; ADR-057).

``effective(key) = default ⊕ preset ⊕ tenant ⊕ institution ⊕ campus`` over **published**
versions only. ``deep`` keys merge objects recursively; every other key is replaced. Code reads
configuration only through :func:`get_effective_config` / :func:`effective_config`.

Results are cached per tenant and scope under a per-tenant generation token that every publish
or rollback replaces, immediately and again after commit (a reader inside the publishing
transaction window can't keep a stale entry). While a publish of this connection is not yet
committed, results are computed but **not stored**: if that transaction rolls back, nothing
uncommitted can survive in the cache (Phase 6 M1: publish checks read configuration inside the
publishing transaction).
"""

from __future__ import annotations

import copy
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils.module_loading import import_string

from apps.core.ids import new_id
from apps.core.tenancy import require_tenant
from apps.core.tenancy.keys import tenant_cache_key
from apps.customization.registry import declared_settings
from apps.customization.scopes import TENANT_SCOPE, ConfigScope

_TTL = 300


def deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for key, value in override.items():
            out[key] = deep_merge(base.get(key), value) if key in base else copy.deepcopy(value)
        return out
    return copy.deepcopy(override)


def _generation() -> str:
    key = tenant_cache_key("config-gen")
    value = cache.get(key)
    if value is None:
        cache.add(key, new_id().hex, timeout=None)
        value = cache.get(key)
    return str(value)


def invalidate() -> None:
    """New generation now and after commit (call inside the publishing transaction)."""
    tenant = require_tenant()

    def bump() -> None:
        cache.set(tenant_cache_key("config-gen", tenant=tenant.id), new_id().hex, timeout=None)

    bump.config_publish = True  # type: ignore[attr-defined]  # marks a pending publish
    bump()
    transaction.on_commit(bump)


def _publish_pending() -> bool:
    """Whether this connection holds an uncommitted publish (its on-commit bump is queued;
    Django discards callbacks of rolled-back transactions and savepoints)."""
    pending = transaction.get_connection().run_on_commit
    return any(getattr(entry[1], "config_publish", False) for entry in pending)


def _preset_layer(scope: ConfigScope) -> dict[str, Any]:
    """Institution-type preset values (M2 hook ``CUSTOMIZATION_PRESET_LAYER``)."""
    hook = getattr(settings, "CUSTOMIZATION_PRESET_LAYER", "")
    return dict(import_string(hook)(scope)) if hook else {}


def _resolve(scope: ConfigScope) -> dict[str, Any]:
    from apps.customization.models import ConfigVersion

    specs = declared_settings()
    values: dict[str, Any] = {key: copy.deepcopy(spec.default) for key, spec in specs.items()}
    layers = [_preset_layer(scope)]
    published = {
        (row.scope_type, row.institution_id, row.campus_id): row.data
        for row in ConfigVersion.objects.filter(status=ConfigVersion.Status.PUBLISHED)
        .filter(scope_type__in=[s.kind for s in scope.chain()])
        .only("scope_type", "institution_id", "campus_id", "data")
    }
    for link in scope.chain():
        layers.append(published.get((link.kind, link.institution_id, link.campus_id), {}))
    for layer in layers:
        for key, value in layer.items():
            spec = specs.get(key)
            if spec is None:
                continue  # a key removed from the catalogue is ignored, never served
            values[key] = deep_merge(values[key], value) if spec.merge == "deep" else value
    return values


def effective_config(scope: ConfigScope = TENANT_SCOPE) -> dict[str, Any]:
    key = tenant_cache_key("config", _generation(), scope.cache_part())
    cached = cache.get(key)
    if cached is not None:
        return dict(cached)
    values = _resolve(scope)
    if not _publish_pending():
        cache.set(key, values, timeout=_TTL)
    return values


def get_effective_config(scope: ConfigScope, key: str) -> Any:
    if key not in declared_settings():
        raise KeyError(f"Undeclared setting {key!r}.")
    return effective_config(scope)[key]
