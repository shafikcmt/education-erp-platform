"""Entitlement expiry sweep (Phase 4 M3; platform operation P19, mechanism I).

``module_registry.sweep_entitlements`` (platform task) ends lapsed trials, add-ons and module
overrides in the registry and fans out one ``module_registry.recompute_entitlements`` tenant
task per affected tenant, which rewrites that tenant's snapshot in its own transaction.
"""

from __future__ import annotations

import uuid

from django.db import transaction
from django.utils import timezone

from apps.core.tasking import platform_task
from apps.core.tenancy.platform import SYSTEM, platform_scope
from apps.module_registry.entitlements import recompute
from apps.module_registry.models import ModuleOverride
from apps.tenancy.rules import TenantStatus
from apps.tenancy.tasking import tenant_task


@platform_task(name="module_registry.sweep_entitlements", operation="P19")
def sweep_entitlements() -> int:
    from apps.billing.models import Subscription, SubscriptionItem

    now = timezone.now()
    affected: set[uuid.UUID] = set()
    # Registry writes inside the audited P19 scope; the snapshots are rewritten afterwards,
    # one tenant task (and one tenant transaction) per affected tenant.
    with (
        platform_scope(operation="P19", actor=SYSTEM, reason="Entitlement expiry sweep"),
        transaction.atomic(),
    ):
        trials = Subscription.objects.select_for_update().filter(
            status="trialing", trial_ends_at__lte=now
        )
        affected |= set(trials.values_list("tenant_id", flat=True))
        Subscription.objects.filter(status="trialing", trial_ends_at__lte=now).update(
            status="expired", updated_at=now
        )
        items = SubscriptionItem.objects.filter(ended_at__isnull=True, valid_until__lte=now)
        affected |= set(items.values_list("tenant_id", flat=True))
        items.update(ended_at=now, updated_at=now)
        overrides = ModuleOverride.objects.filter(ended_at__isnull=True, expires_at__lte=now)
        affected |= set(overrides.values_list("tenant_id", flat=True))
        overrides.update(ended_at=now, updated_at=now)
    for tenant_id in sorted(affected):
        recompute_entitlements.delay(tenant_id=str(tenant_id))
    return len(affected)


@tenant_task(
    name="module_registry.recompute_entitlements",
    statuses=(TenantStatus.ACTIVE, TenantStatus.SUSPENDED, TenantStatus.OFFBOARDING),
)
def recompute_entitlements(*, tenant_id: uuid.UUID) -> int:
    resolved = recompute(tenant_id)
    return sum(1 for _, on, _ in resolved.values() if on)
