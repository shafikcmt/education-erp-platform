"""Module overrides and feature flags (Phase 4 M2; ADR-052, ADR-053).

* **Overrides (P18):** a Super Admin or ``platform_billing`` grant or revocation of one module
  for one tenant, with a reason and an optional expiry; ``billing.subscription.manage`` with
  step-up. Written to both logs; entitlements are recomputed from M3.
* **Feature flags (P17):** rollout controls (ADR-053), ``module_registry.flag.manage``.
  :func:`flag_enabled` evaluates a flag for a tenant from data only: explicit tenant list,
  plan list, then a stable percentage bucket of the tenant id, then the default.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.services import record
from apps.billing.services import SUBSCRIPTION_MANAGE, _both_logs, _reason, _tenant
from apps.core.tenancy.platform import platform_scope
from apps.module_registry.models import FeatureFlag, Module, ModuleOverride

if TYPE_CHECKING:
    from django.http import HttpRequest

    from apps.identity.models import User

FLAG_MANAGE = "module_registry.flag.manage"
_RULE_KEYS = {"percentage", "plans", "tenants"}


def set_override(
    *,
    actor: User,
    tenant_id: uuid.UUID,
    module_code: str,
    kind: str,
    reason: str,
    expires_at: datetime | None = None,
    request: HttpRequest | None = None,
) -> ModuleOverride:
    cleaned = _reason(reason)
    if kind not in ModuleOverride.Kind.values:
        raise ValidationError({"kind": "Use grant or revoke."})
    if expires_at is not None and expires_at <= timezone.now():
        raise ValidationError({"expires_at": "Must be in the future."})
    with platform_scope(
        operation="P18", actor=actor, reason=cleaned, permission=SUBSCRIPTION_MANAGE
    ):
        tenant = _tenant(tenant_id)
        module = Module.objects.filter(code=module_code, deprecated_at__isnull=True).first()
        if module is None or module.category == Module.Category.PLATFORM:
            raise ValidationError({"module": "Only a non-platform module can be overridden."})
        try:
            with transaction.atomic():
                ModuleOverride.objects.filter(
                    tenant=tenant, module=module, ended_at__isnull=True
                ).update(ended_at=timezone.now(), updated_at=timezone.now())
                override = ModuleOverride.objects.create(
                    tenant=tenant,
                    module=module,
                    kind=kind,
                    reason=cleaned,
                    expires_at=expires_at,
                    created_by=actor.pk,
                )
        except IntegrityError:  # pragma: no cover - serialised by the update above
            raise ValidationError({"module": "Try again."}) from None
        _both_logs(
            "module_registry.override.set",
            tenant,
            actor=actor,
            request=request,
            metadata={"module_code": module_code, "kind": kind, "reason": cleaned},
        )
    return override


def end_override(
    *,
    actor: User,
    tenant_id: uuid.UUID,
    module_code: str,
    reason: str,
    request: HttpRequest | None = None,
) -> int:
    cleaned = _reason(reason)
    with platform_scope(
        operation="P18", actor=actor, reason=cleaned, permission=SUBSCRIPTION_MANAGE
    ):
        tenant = _tenant(tenant_id)
        ended = ModuleOverride.objects.filter(
            tenant=tenant, module__code=module_code, ended_at__isnull=True
        ).update(ended_at=timezone.now(), updated_at=timezone.now())
        if ended:
            _both_logs(
                "module_registry.override.ended",
                tenant,
                actor=actor,
                request=request,
                metadata={"module_code": module_code, "reason": cleaned},
            )
    return ended


def _rules(rules: dict[str, Any]) -> dict[str, Any]:
    unknown = set(rules) - _RULE_KEYS
    if unknown:
        raise ValidationError({"rules": f"Unknown rule keys: {', '.join(sorted(unknown))}."})
    cleaned: dict[str, Any] = {}
    if "percentage" in rules:
        pct = rules["percentage"]
        if not isinstance(pct, int) or isinstance(pct, bool) or not 0 <= pct <= 100:
            raise ValidationError({"rules": "percentage must be 0-100."})
        cleaned["percentage"] = pct
    for key in ("plans", "tenants"):
        if key in rules:
            values = rules[key]
            if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                raise ValidationError({"rules": f"{key} must be a list of strings."})
            if key == "tenants":
                try:
                    values = [str(uuid.UUID(v)) for v in values]
                except ValueError:
                    raise ValidationError({"rules": "tenants must be tenant ids."}) from None
            cleaned[key] = sorted(set(values))[:500]
    return cleaned


def set_flag(
    *,
    actor: User,
    key: str,
    default_enabled: bool,
    rules: dict[str, Any] | None = None,
    description: str = "",
    request: HttpRequest | None = None,
) -> FeatureFlag:
    with platform_scope(operation="P17", actor=actor, reason=f"flag {key}", permission=FLAG_MANAGE):
        cleaned = _rules(rules or {})
        try:
            with transaction.atomic():
                flag, _ = FeatureFlag.objects.update_or_create(
                    key=key,
                    defaults={
                        "default_enabled": bool(default_enabled),
                        "rules": cleaned,
                        "description": description[:255],
                    },
                )
        except IntegrityError:
            raise ValidationError({"key": "Invalid flag key."}) from None
        record(
            "module_registry.flag.changed",
            actor=actor,
            request=request,
            target_type="module_registry.featureflag",
            target_id=flag.pk,
            metadata={"flag_key": key, "default_enabled": bool(default_enabled)},
        )
    return flag


def _bucket(key: str, tenant_id: uuid.UUID) -> int:
    digest = hashlib.sha256(f"{key}:{tenant_id}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % 100


def flag_enabled(key: str, *, tenant_id: uuid.UUID | None = None, plan_code: str = "") -> bool:
    """Data-only evaluation (no per-tenant code paths, CLAUDE.md §4). Unknown flags are off."""
    flag = FeatureFlag.objects.filter(key=key).first()
    if flag is None:
        return False
    rules = flag.rules if isinstance(flag.rules, dict) else {}
    if tenant_id is not None and str(tenant_id) in rules.get("tenants", []):
        return True
    if plan_code and plan_code in rules.get("plans", []):
        return True
    if tenant_id is not None and "percentage" in rules:
        return _bucket(key, tenant_id) < int(rules["percentage"])
    return flag.default_enabled
