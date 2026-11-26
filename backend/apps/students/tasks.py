"""Students tasks (Phase 7 M4, M6).

``students.convert_application`` turns an accepted application into a student in the tenant's
own transaction (queued by ``ADMISSIONS_ACCEPTED_HANDLERS`` after the acceptance commits). It is
refused for tenants without the ``students`` module.

``students.run_import`` runs an import's dry run or apply (M6). ``students.import_housekeeping``
(platform operation **P28**, mechanism I) fans out ``students.purge_imports`` per tenant: import
jobs and their files are deleted after the retention period.
"""

from __future__ import annotations

import uuid

from apps.core.tasking import platform_task
from apps.tenancy.rules import TenantStatus
from apps.tenancy.tasking import tenant_task


@tenant_task(name="students.convert_application", module="students")
def convert_application(*, tenant_id: uuid.UUID, application_id: str) -> str | None:
    from apps.students.conversion import convert

    student = convert(application_id)
    return str(student.pk) if student is not None else None


@tenant_task(name="students.run_import", module="students")
def run_import(*, tenant_id: uuid.UUID, job_id: str, apply: bool = False) -> str:
    """Dry run or apply an import (Phase 7 M6). The file is read here, in the task body."""
    import logging

    from apps.files import services as files
    from apps.files.models import StoredFile
    from apps.students import imports
    from apps.students.models import ImportJob

    job = ImportJob.objects.filter(pk=job_id).first()
    if job is None:
        return "missing"
    content: bytes | None = None
    stored = StoredFile.objects.filter(pk=job.file_id).first()
    try:
        content = files.read_content(file=stored) if stored is not None else None
    except Exception:  # unreadable or gone: the job fails with a clear message
        logging.getLogger(__name__).warning("students.import_unreadable", exc_info=True)
    done = imports.run(job_id, apply_rows=apply, content=content)
    return done.status if done is not None else "skipped"


@platform_task(name="students.import_housekeeping", operation="P28")
def import_housekeeping() -> int:
    """P28: fan out ``students.purge_imports`` to every active or suspended tenant."""
    from apps.tenancy.models import Tenant

    tenant_ids = list(
        Tenant.objects.filter(status__in=(TenantStatus.ACTIVE, TenantStatus.SUSPENDED)).values_list(
            "id", flat=True
        )
    )
    for tenant_id in tenant_ids:
        purge_imports.delay(tenant_id=str(tenant_id))
    return len(tenant_ids)


@tenant_task(name="students.purge_imports", statuses=(TenantStatus.ACTIVE, TenantStatus.SUSPENDED))
def purge_imports(*, tenant_id: uuid.UUID) -> int:
    """Delete import jobs (their reports hold personal data) and their files after the
    retention period; ``files`` housekeeping (P27) then removes the objects."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.files import services as files
    from apps.files.models import StoredFile
    from apps.students.imports import RETENTION_DAYS
    from apps.students.models import ImportJob

    old = ImportJob.objects.filter(created_at__lt=timezone.now() - timedelta(days=RETENTION_DAYS))
    file_ids = list(old.values_list("file_id", flat=True))
    for stored in StoredFile.objects.filter(pk__in=file_ids):
        files.delete_file(file=stored, actor_id=None)
    count, _ = old.delete()
    return count
