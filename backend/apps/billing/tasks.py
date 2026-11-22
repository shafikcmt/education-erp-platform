"""Usage metering (Phase 4 M7; plan §2): one row per tenant, metric and day.

``billing.record_usage`` (platform task, P19 system iteration) fans out one
``billing.record_tenant_usage`` tenant task per active or suspended tenant; each counts the
tenant's active institutions and campuses inside its own transaction (RLS) and upserts today's
rows. Phase 4 meters only these two metrics; later phases add their own.
"""

from __future__ import annotations

import uuid

from django.utils import timezone

from apps.core.tasking import platform_task
from apps.tenancy.rules import TenantStatus
from apps.tenancy.tasking import tenant_task

METERED = (TenantStatus.ACTIVE, TenantStatus.SUSPENDED)


@platform_task(name="billing.record_usage", operation="P19")
def record_usage() -> int:
    from apps.tenancy.models import Tenant

    tenant_ids = list(Tenant.objects.filter(status__in=METERED).values_list("id", flat=True))
    for tenant_id in tenant_ids:
        record_tenant_usage.delay(tenant_id=str(tenant_id))
    return len(tenant_ids)


@tenant_task(name="billing.record_tenant_usage", statuses=METERED)
def record_tenant_usage(*, tenant_id: uuid.UUID) -> dict[str, int]:
    from apps.billing.models import UsageRecord
    from apps.tenancy.models import Campus, Institution

    counts = {
        UsageRecord.Metric.INSTITUTIONS: Institution.objects.filter(
            archived_at__isnull=True
        ).count(),
        UsageRecord.Metric.CAMPUSES: Campus.objects.filter(archived_at__isnull=True).count(),
    }
    today = timezone.now().date()
    for metric, value in counts.items():
        UsageRecord.objects.update_or_create(metric=metric, period=today, defaults={"value": value})
    return {str(k): v for k, v in counts.items()}
