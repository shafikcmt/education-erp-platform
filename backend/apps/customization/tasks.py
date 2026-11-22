"""Workflow SLA sweep (Phase 5 M4; platform operation P24, mechanism I)."""

from __future__ import annotations

import uuid

from apps.core.tasking import platform_task
from apps.tenancy.rules import TenantStatus
from apps.tenancy.tasking import tenant_task


@platform_task(name="customization.sweep_workflow_sla", operation="P24")
def sweep_workflow_sla() -> int:
    """Enqueue one SLA check per active tenant (instances are tenant data: RLS)."""
    from apps.tenancy.models import Tenant

    tenant_ids = list(
        Tenant.objects.filter(status=TenantStatus.ACTIVE).values_list("id", flat=True)
    )
    for tenant_id in tenant_ids:
        check_workflow_sla.delay(tenant_id=str(tenant_id))
    return len(tenant_ids)


@tenant_task(name="customization.check_workflow_sla")
def check_workflow_sla(*, tenant_id: uuid.UUID) -> int:
    from apps.customization.workflows import mark_overdue

    return mark_overdue()
