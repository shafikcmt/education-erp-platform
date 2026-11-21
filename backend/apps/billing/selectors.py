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
