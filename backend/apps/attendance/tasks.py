"""Attendance tasks (Phase 8 M5).

``attendance.send_absence_alerts`` notifies guardians after a register is submitted (queued by
``ATTENDANCE_SUBMITTED_HANDLERS``). ``attendance.nightly`` (platform operation **P29**, mechanism
I) fans out ``attendance.nightly_tenant`` per tenant: lock registers past their lock date, then
refresh low-attendance flags and notify class teachers.
"""

from __future__ import annotations

import uuid

from apps.core.tasking import platform_task
from apps.tenancy.rules import TenantStatus
from apps.tenancy.tasking import tenant_task


@tenant_task(name="attendance.send_absence_alerts", module="attendance")
def send_absence_alerts(*, tenant_id: uuid.UUID, register_id: str) -> int:
    from apps.attendance.alerts import send_alerts

    return send_alerts(register_id)


@platform_task(name="attendance.nightly", operation="P29")
def nightly() -> int:
    """P29: fan out ``attendance.nightly_tenant`` to every active tenant."""
    from apps.tenancy.models import Tenant

    tenant_ids = list(
        Tenant.objects.filter(status=TenantStatus.ACTIVE).values_list("id", flat=True)
    )
    for tenant_id in tenant_ids:
        nightly_tenant.delay(tenant_id=str(tenant_id))
    return len(tenant_ids)


@tenant_task(name="attendance.nightly_tenant", module="attendance")
def nightly_tenant(*, tenant_id: uuid.UUID) -> dict[str, int]:
    from apps.attendance.alerts import nightly as run

    return run()
