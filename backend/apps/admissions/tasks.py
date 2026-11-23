"""Admissions housekeeping (Phase 6 M5; platform operation **P26**, mechanism I).

``admissions.housekeeping`` fans out ``admissions.purge`` per active tenant: unverified public
drafts past their 48-hour expiry are deleted (personal data) and open cycles past their closing
date are closed.
"""

from __future__ import annotations

import uuid

from apps.core.tasking import platform_task
from apps.tenancy.rules import TenantStatus
from apps.tenancy.tasking import tenant_task


@platform_task(name="admissions.housekeeping", operation="P26")
def housekeeping() -> int:
    from apps.tenancy.models import Tenant

    tenant_ids = list(
        Tenant.objects.filter(status=TenantStatus.ACTIVE).values_list("id", flat=True)
    )
    for tenant_id in tenant_ids:
        purge.delay(tenant_id=str(tenant_id))
    return len(tenant_ids)


@tenant_task(name="admissions.purge")
def purge(*, tenant_id: uuid.UUID) -> dict[str, int]:
    from apps.admissions.public import close_past_cycles, purge_drafts

    return {"drafts": purge_drafts(), "cycles": close_past_cycles()}
