"""Entitlement resolution (Phase 4 M3; ADR-052, ADR-054).

``entitled(tenant) = closure(platform | plan | active add-ons | grants) - revocations``

* **Plan modules** count while the subscription is ``trialing`` (and the trial has not ended),
  ``active`` or ``past_due``. ``suspended``, ``canceled`` and ``expired`` keep only platform
  modules; the data is never deleted (Q3: ``403 module_not_entitled``).
* **Dependencies:** a candidate is enabled only if every dependency is enabled; a broken
  dependency disables it (``missing_dependency``), never silently enables the dependency.
* **Not built** modules (``available = False``) are never enabled (``not_built``).
* :func:`recompute` writes the snapshot (``module_registry_tenantmodule``) inside the tenant's
  transaction and bumps the tenant's cache version. :func:`enabled_modules` reads the snapshot
  through a cache keyed by that version; :func:`require_module` is the service-layer guard.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.cache import cache
from django.db import connection
from django.utils import timezone

from apps.core.tenancy import require_tenant
from apps.core.tenancy.exceptions import TenantContextNotApplied
from apps.core.tenancy.keys import tenant_cache_key
from apps.core.tenancy.transaction import applied_tenant_id
from apps.module_registry.errors import ModuleNotEntitledError
from apps.module_registry.models import Module, ModuleOverride, TenantModule
from apps.rbac.engine import bump_tenant_version, tenant_cache_version

PLAN_STATUSES = frozenset({"trialing", "active", "past_due"})
_CACHE_TTL = 300


def _modules() -> dict[str, Module]:
    return {m.code: m for m in Module.objects.filter(deprecated_at__isnull=True)}


def resolve(tenant_id: uuid.UUID) -> dict[str, tuple[str, bool, str]]:
    """``{module: (source, enabled, disabled_reason)}`` from the registry data (platform rows
    are self-scoped, so this works inside the tenant's own transaction)."""
    from apps.billing.models import Subscription, SubscriptionItem

    now = timezone.now()
    modules = _modules()
    candidates: dict[str, str] = {
        code: "platform" for code, m in modules.items() if m.category == Module.Category.PLATFORM
    }
    sub = Subscription.objects.filter(tenant_id=tenant_id).select_related("plan").first()
    if (
        sub is not None
        and sub.status in PLAN_STATUSES
        and not (
            sub.status == "trialing" and sub.trial_ends_at is not None and sub.trial_ends_at <= now
        )
    ):
        for code in sub.plan.plan_modules.values_list("module__code", flat=True):
            candidates.setdefault(str(code), "plan")
        for code in (
            SubscriptionItem.objects.filter(
                tenant_id=tenant_id, ended_at__isnull=True, addon__module__isnull=False
            )
            .exclude(valid_until__lte=now)
            .values_list("addon__module__code", flat=True)
        ):
            candidates.setdefault(str(code), "addon")
    revoked: set[str] = set()
    for code, kind in (
        ModuleOverride.objects.filter(tenant_id=tenant_id, ended_at__isnull=True)
        .exclude(expires_at__lte=now)
        .values_list("module__code", "kind")
    ):
        if kind == ModuleOverride.Kind.GRANT:
            candidates[str(code)] = "override"
        else:
            revoked.add(str(code))
    result: dict[str, tuple[str, bool, str]] = {}
    enabled = {c for c in candidates if c not in revoked and modules[c].available}
    changed = True
    while changed:  # drop modules whose dependencies are not enabled, until stable
        changed = False
        for code in sorted(enabled):
            if any(dep not in enabled for dep in modules[code].dependencies):
                enabled.discard(code)
                changed = True
    for code, source in candidates.items():
        if code in revoked:
            reason = "revoked"
        elif not modules[code].available:
            reason = "not_built"
        elif code not in enabled:
            reason = "missing_dependency"
        else:
            reason = ""
        result[code] = (source, code in enabled, reason)
    return result


def _assert_tenant_transaction(tenant_id: uuid.UUID) -> None:
    ctx = require_tenant()
    if ctx.id != tenant_id or applied_tenant_id(connection) != ctx.id:
        raise TenantContextNotApplied("Entitlements are recomputed inside tenant_atomic().")


def recompute(tenant_id: uuid.UUID) -> dict[str, tuple[str, bool, str]]:
    """Rewrite the tenant's snapshot (inside its transaction) and invalidate its cache."""
    _assert_tenant_transaction(tenant_id)
    resolved = resolve(tenant_id)
    TenantModule.objects.all().delete()
    TenantModule.objects.bulk_create(
        [
            TenantModule(module_id=code, source=source, enabled=on, disabled_reason=reason)
            for code, (source, on, reason) in sorted(resolved.items())
        ]
    )
    bump_tenant_version(tenant_id)
    return resolved


def snapshot(tenant_id: uuid.UUID) -> dict[str, tuple[str, bool, str]]:
    """The stored snapshot of the current tenant (what enforcement uses). Before the first
    recompute, the built platform modules."""
    ctx = require_tenant()
    if tenant_id != ctx.id:
        raise TenantContextNotApplied("The snapshot is read for the current tenant only.")
    rows = {
        str(r.module_id): (r.source, r.enabled, r.disabled_reason)
        for r in TenantModule.objects.all()
    }
    if rows:
        return rows
    return {
        code: ("platform", True, "")
        for code, m in _modules().items()
        if m.category == Module.Category.PLATFORM and m.available
    }


def _cache_key(tenant_id: uuid.UUID) -> str:
    return tenant_cache_key("entitlements", tenant_cache_version(tenant_id), tenant=tenant_id)


def enabled_modules(tenant_id: uuid.UUID | None = None) -> frozenset[str]:
    """Enabled modules of the current tenant (from the snapshot, cached per tenant version).
    Built platform modules are always included, even before the first snapshot exists."""
    ctx = require_tenant()
    tenant_id = tenant_id or ctx.id
    if tenant_id != ctx.id:
        raise TenantContextNotApplied("Entitlements are read for the current tenant only.")
    key = _cache_key(tenant_id)
    cached: Any = cache.get(key)
    if cached is not None:
        return frozenset(cached)
    platform = {
        code
        for code, m in _modules().items()
        if m.category == Module.Category.PLATFORM and m.available
    }
    snapshot = set(TenantModule.objects.filter(enabled=True).values_list("module_id", flat=True))
    result = frozenset(platform | {str(c) for c in snapshot})
    cache.set(key, sorted(result), timeout=_CACHE_TTL)
    return result


def summary(tenant_id: uuid.UUID) -> dict[str, Any]:
    """For ``/me/context/``: enabled modules and the flags evaluated for this tenant."""
    from apps.billing.models import Subscription
    from apps.module_registry.models import FeatureFlag
    from apps.module_registry.services import flag_enabled

    sub = Subscription.objects.filter(tenant_id=tenant_id).select_related("plan").first()
    plan_code = sub.plan.code if sub else ""
    flags = {
        key: flag_enabled(key, tenant_id=tenant_id, plan_code=plan_code)
        for key in FeatureFlag.objects.order_by("key").values_list("key", flat=True)
    }
    return {"modules": sorted(enabled_modules(tenant_id)), "flags": flags}


def is_entitled(code: str) -> bool:
    return code in enabled_modules()


def require_module(code: str) -> None:
    """Service-layer guard (ADR-052): raise ``module_not_entitled`` unless enabled."""
    if not is_entitled(code):
        raise ModuleNotEntitledError()
