"""File tasks (Phase 6 M3; ADR-064).

* ``files.verify_upload`` (tenant task): checks the uploaded object (size and type against the
  declaration and the purpose) and scans it, outside any open tenant transaction for the I/O.
* ``files.housekeeping`` (platform operation **P27**, mechanism I) fans out ``files.purge`` per
  tenant: unconfirmed uploads past their expiry, rejected and deleted files lose their object.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.utils import timezone

from apps.core.tasking import platform_task
from apps.files import storage
from apps.files.scanning import scan
from apps.tenancy.rules import TenantStatus
from apps.tenancy.tasking import tenant_task

GRACE = timedelta(hours=24)


@tenant_task(name="files.verify_upload")
def verify_upload(*, tenant_id: uuid.UUID, file_id: str) -> str:
    """Runs inside the tenant's transaction (``TenantTask``); storage I/O is allowed in a task
    body."""
    from apps.files import services
    from apps.files.models import StoredFile

    row = (
        StoredFile.objects.select_for_update()
        .filter(pk=file_id, status=StoredFile.Status.VERIFYING)
        .first()
    )
    if row is None:
        return "skipped"
    observed = storage.head(row.key)
    row = services.verify(row, observed, scan(row.key) if observed else "unscanned")
    if row.status == StoredFile.Status.REJECTED and observed is not None:
        storage.delete(row.key)
    return str(row.status)


@platform_task(name="files.housekeeping", operation="P27")
def housekeeping() -> int:
    from apps.tenancy.models import Tenant

    tenant_ids = list(
        Tenant.objects.filter(status__in=(TenantStatus.ACTIVE, TenantStatus.SUSPENDED)).values_list(
            "id", flat=True
        )
    )
    for tenant_id in tenant_ids:
        purge.delay(tenant_id=str(tenant_id))
    return len(tenant_ids)


@tenant_task(name="files.purge", statuses=(TenantStatus.ACTIVE, TenantStatus.SUSPENDED))
def purge(*, tenant_id: uuid.UUID) -> int:
    """Unconfirmed uploads past their expiry become deleted; deleted and rejected files older
    than the grace period lose their object and their row."""
    from apps.files.models import StoredFile

    now = timezone.now()
    StoredFile.objects.filter(
        status=StoredFile.Status.AWAITING_UPLOAD, upload_expires_at__lt=now - GRACE
    ).update(status=StoredFile.Status.DELETED, deleted_at=now)
    doomed = list(
        StoredFile.objects.filter(
            status__in=(StoredFile.Status.DELETED, StoredFile.Status.REJECTED),
            deleted_at__lt=now - GRACE,
        ).values_list("pk", "key")
    )
    for _, key in doomed:
        storage.delete(key)  # S3 deletes are idempotent: a never-uploaded key is fine
    StoredFile.objects.filter(pk__in=[pk for pk, _ in doomed]).delete()
    return len(doomed)
