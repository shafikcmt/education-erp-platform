"""Probe Celery tasks for the task-isolation tests (tests only; Phase 3 M7)."""

from __future__ import annotations

import uuid
from typing import Any

from celery.exceptions import SoftTimeLimitExceeded
from django.db import connection

from apps.core.tasking import platform_task
from apps.core.tenancy import current_tenant
from apps.tenancy.rules import TenantStatus
from apps.tenancy.tasking import tenant_task
from tests.isolation_app.models import ProbeRecord


def _seen() -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.tenant_id', true)")
        setting = cursor.fetchone()[0] or ""
        cursor.execute("SELECT DISTINCT tenant_id::text FROM isolation_probe_record")
        raw = sorted(row[0] for row in cursor.fetchall())
    ctx = current_tenant()
    return {"setting": setting, "raw": raw, "context": str(ctx.id) if ctx else None}


@tenant_task(name="probe.tenant_write_and_read")
def tenant_write_and_read(*, tenant_id: uuid.UUID, name: str = "") -> dict[str, Any]:
    if name:
        ProbeRecord.objects.create(name=name)
    names = sorted(ProbeRecord.objects.values_list("name", flat=True))
    return {"tenant_id": str(tenant_id), "names": names, **_seen()}


@tenant_task(name="probe.tenant_fail")
def tenant_fail(*, tenant_id: uuid.UUID, soft: bool = False) -> None:
    ProbeRecord.objects.create(name="never-committed")
    if soft:
        raise SoftTimeLimitExceeded()
    raise RuntimeError("probe failure")


@tenant_task(
    name="probe.tenant_suspended_ok", statuses=(TenantStatus.ACTIVE, TenantStatus.SUSPENDED)
)
def tenant_suspended_ok(*, tenant_id: uuid.UUID) -> str:
    return "ran"


@platform_task(name="probe.platform_sees", operation="P12")
def platform_sees() -> dict[str, Any]:
    return _seen()


@platform_task(name="probe.platform_tenant_query", operation="P12")
def platform_tenant_query() -> int:
    return ProbeRecord.objects.count()  # no tenant context: TenantManager raises
