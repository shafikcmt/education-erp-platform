"""Read helpers of billing used by other modules through settings hooks (Phase 4 M3)."""

from __future__ import annotations

import uuid
from typing import Any

from apps.billing.models import Subscription


def plan_limits(tenant_id: uuid.UUID) -> dict[str, Any]:
    """The tenant's plan limits (``TENANCY_PLAN_LIMITS`` hook); ``{}`` without a subscription.
    Works with or without a tenant context (self-scoped rows)."""
    sub = Subscription.objects.filter(tenant_id=tenant_id).select_related("plan").first()
    limits = sub.plan.limits if sub is not None else {}
    return dict(limits) if isinstance(limits, dict) else {}


def _addons(tenant_id: uuid.UUID) -> list[dict[str, Any]]:
    from django.db.models import Q
    from django.utils import timezone

    from apps.billing.models import SubscriptionItem

    now = timezone.now()
    rows = (
        SubscriptionItem.objects.filter(tenant_id=tenant_id, ended_at__isnull=True)
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
        .select_related("addon")
        .order_by("addon__code")
    )
    return [
        {
            "code": r.addon.code,
            "name": r.addon.name,
            "valid_from": r.valid_from,
            "valid_until": r.valid_until,
        }
        for r in rows
    ]


def _subscription_fields(tenant_id: uuid.UUID) -> dict[str, Any]:
    sub = Subscription.objects.filter(tenant_id=tenant_id).select_related("plan").first()
    return {
        "plan": {"code": sub.plan.code, "name": sub.plan.name} if sub else None,
        "status": sub.status if sub else None,
        "trial_ends_at": sub.trial_ends_at if sub else None,
        "current_period_end": sub.current_period_end if sub else None,
        "addons": _addons(tenant_id),
    }


def subscription_detail(tenant_id: uuid.UUID) -> dict[str, Any]:
    """Platform view of one tenant's subscription (registry rows, no tenant context). Modules
    are resolved live from the registry data, as the next recompute would store them."""
    from django.db.models import Q
    from django.utils import timezone

    from apps.module_registry.entitlements import resolve
    from apps.module_registry.models import ModuleOverride

    now = timezone.now()
    overrides = (
        ModuleOverride.objects.filter(tenant_id=tenant_id, ended_at__isnull=True)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .order_by("module_id")
    )
    return {
        "tenant_id": tenant_id,
        **_subscription_fields(tenant_id),
        "overrides": [
            {
                "module": o.module_id,
                "kind": o.kind,
                "reason": o.reason,
                "expires_at": o.expires_at,
                "created_at": o.created_at,
            }
            for o in overrides
        ],
        "modules": _module_states(resolve(tenant_id)),
    }


def _module_states(resolved: dict[str, tuple[str, bool, str]]) -> list[dict[str, Any]]:
    return [
        {"code": code, "source": source, "enabled": on, "reason": reason}
        for code, (source, on, reason) in sorted(resolved.items())
    ]


def tenant_subscription(tenant_id: uuid.UUID) -> dict[str, Any]:
    """The current tenant's own view (inside its transaction). Modules come from the stored
    snapshot, which is what enforcement uses; limits show the current usage."""
    from apps.module_registry.entitlements import snapshot
    from apps.tenancy.limits import limits_usage
    from apps.tenancy.models import Tenant

    return {
        **_subscription_fields(tenant_id),
        "modules": _module_states(snapshot(tenant_id)),
        "limits": limits_usage(Tenant.objects.get(pk=tenant_id)),
    }
