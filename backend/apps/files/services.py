"""File services (Phase 6 M3; ADR-064).

* ``request_upload`` validates the purpose's type, size and per-owner count and the tenant's
  storage quota (plan key ``max_storage_mb``), stores a row under a server-chosen key and
  returns a presigned POST bound to that key, type and size.
* ``confirm_upload`` hands the object to the verification task after commit.
* ``download_url`` issues a short-lived link for a ready file. Callers authorise access to the
  owning object first; this layer adds the file rules (never infected, applicants only clean).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.http import HttpRequest
from django.utils import timezone

from apps.audit.services import record
from apps.core.tenancy.keys import tenant_storage_key
from apps.files import storage
from apps.files.models import StoredFile
from apps.files.purposes import declared_purposes

LIVE = (StoredFile.Status.AWAITING_UPLOAD, StoredFile.Status.VERIFYING, StoredFile.Status.READY)
MB = 1024 * 1024


def _purpose(code: str) -> Any:
    purpose = declared_purposes().get(code)
    if purpose is None:
        raise ValidationError({"purpose": "Unknown file purpose."})
    return purpose


def usage_bytes() -> int:
    total = StoredFile.objects.filter(status__in=LIVE).aggregate(total=Sum("declared_size"))[
        "total"
    ]
    return int(total or 0)


def _check_quota(size: int) -> None:
    from apps.customization.quotas import limit

    cap_mb = limit("max_storage_mb")
    if cap_mb and usage_bytes() + size > cap_mb * MB:
        raise ValidationError({"quota": f"Your plan's storage ({cap_mb} MB) is full."})


@transaction.atomic
def request_upload(
    *,
    purpose: str,
    name: str,
    size: int,
    content_type: str,
    owner_type: str = "",
    owner_id: uuid.UUID | None = None,
    uploaded_by: uuid.UUID | None = None,
    request: HttpRequest | None = None,
) -> tuple[StoredFile, dict[str, Any]]:
    """The caller has authorised the upload for ``owner``; returns the row and the POST form."""
    spec = _purpose(purpose)
    content_type = (content_type or "").split(";")[0].strip().lower()
    if content_type not in spec.types:
        raise ValidationError({"content_type": "This file type is not accepted here."})
    if not 0 < size <= spec.max_bytes:
        raise ValidationError({"size": f"Files here are at most {spec.max_bytes // MB or 1} MB."})
    if owner_id is not None and (
        StoredFile.objects.filter(
            owner_type=owner_type, owner_id=owner_id, purpose=purpose, status__in=LIVE
        ).count()
        >= spec.max_per_owner
    ):
        raise ValidationError({"purpose": f"At most {spec.max_per_owner} files here."})
    _check_quota(size)
    file_id = uuid.uuid4()
    row = StoredFile.objects.create(
        purpose=purpose,
        key=tenant_storage_key("files", purpose.replace(".", "-"), file_id.hex),
        owner_type=owner_type,
        owner_id=owner_id,
        original_name=(name or "file")[:200],
        content_type=content_type,
        declared_size=size,
        uploaded_by=uploaded_by,
        upload_expires_at=timezone.now() + timedelta(seconds=storage.UPLOAD_SECONDS),
        created_by=uploaded_by,
    )
    record(
        "files.file.upload_requested",
        actor_user_id=uploaded_by,
        request=request,
        target_type="files.file",
        target_id=row.pk,
        metadata={"purpose": purpose, "size": size},
    )
    return row, storage.presigned_post(row.key, content_type, size)


@transaction.atomic
def confirm_upload(*, file: StoredFile, uploaded_by: uuid.UUID | None = None) -> StoredFile:
    row = StoredFile.objects.select_for_update().get(pk=file.pk)
    if uploaded_by is not None and row.uploaded_by != uploaded_by:
        raise PermissionDenied("files.file.upload")
    if row.status != StoredFile.Status.AWAITING_UPLOAD:
        raise ValidationError({"status": "This upload was already confirmed or closed."})
    row.status = StoredFile.Status.VERIFYING
    row.save(update_fields=["status", "updated_at"])
    from apps.files.tasks import verify_upload

    tenant_id = str(row.tenant_id)
    transaction.on_commit(lambda: verify_upload.delay(tenant_id=tenant_id, file_id=str(row.pk)))
    return row


def verify(row: StoredFile, observed: dict[str, Any] | None, scan_result: str) -> StoredFile:
    """Apply what the storage reported (run by the task, inside the tenant transaction)."""
    spec = declared_purposes().get(row.purpose)
    ok = (
        observed is not None
        and spec is not None
        and 0 < observed["size"] <= min(row.declared_size, spec.max_bytes)
        and observed["content_type"].split(";")[0].strip().lower() == row.content_type
    )
    row.status = StoredFile.Status.READY if ok else StoredFile.Status.REJECTED
    row.size = observed["size"] if observed else None
    row.scan_state = scan_result if ok else StoredFile.Scan.PENDING
    row.verified_at = timezone.now()
    if not ok:
        row.deleted_at = row.verified_at  # rejected rows are purged after the grace period
    row.save(
        update_fields=["status", "size", "scan_state", "verified_at", "deleted_at", "updated_at"]
    )
    record(
        "files.file.verified",
        target_type="files.file",
        target_id=row.pk,
        metadata={"status": row.status, "scan": row.scan_state},
    )
    return row


def download_url(*, file: StoredFile, applicant: bool = False) -> str:
    """After the caller authorised the owning object. Infected files are never served;
    applicants only get clean files of purposes that allow it."""
    if file.status != StoredFile.Status.READY or file.scan_state == StoredFile.Scan.INFECTED:
        raise ValidationError({"file": "This file is not available."})
    if applicant:
        spec = declared_purposes().get(file.purpose)
        if spec is None or not spec.applicant_visible or file.scan_state != StoredFile.Scan.CLEAN:
            raise PermissionDenied("files.file.view")
    return storage.presigned_get(file.key, file.original_name)


@transaction.atomic
def delete_file(
    *, file: StoredFile, actor_id: uuid.UUID | None, request: HttpRequest | None = None
) -> None:
    row = StoredFile.objects.select_for_update().get(pk=file.pk)
    if row.status == StoredFile.Status.DELETED:
        return
    row.status, row.deleted_at = StoredFile.Status.DELETED, timezone.now()
    row.save(update_fields=["status", "deleted_at", "updated_at"])
    record(
        "files.file.deleted",
        actor_user_id=actor_id,
        request=request,
        target_type="files.file",
        target_id=row.pk,
        metadata={"purpose": row.purpose},
    )


def read_content(*, file: StoredFile) -> bytes:
    """The content of a ready, not infected file (callers authorised the owning object; used by
    tasks that process uploads server-side, such as imports)."""
    if file.status != StoredFile.Status.READY or file.scan_state == StoredFile.Scan.INFECTED:
        raise ValidationError({"file": "This file is not available."})
    spec = _purpose(file.purpose)
    return storage.read(file.key, spec.max_bytes)
