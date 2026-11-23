"""Stored files (Phase 6 M3; ADR-064).

One row per object in the bucket. The key is chosen by the server (``tenant_storage_key``)
and never by a client. Lifecycle: ``awaiting_upload`` (a presigned POST was issued) →
``verifying`` (the client says it uploaded; a task checks the object) → ``ready`` or
``rejected``; ``deleted`` is a soft delete (the object is removed by housekeeping). The scan
state is separate: ``unscanned`` until a scanner is configured (Phase 18).
"""

from __future__ import annotations

from django.db import models

from apps.core.tenancy.models import TenantScopedModel


class StoredFile(TenantScopedModel):
    class Status(models.TextChoices):
        AWAITING_UPLOAD = "awaiting_upload", "Awaiting upload"
        VERIFYING = "verifying", "Verifying"
        READY = "ready", "Ready"
        REJECTED = "rejected", "Rejected"
        DELETED = "deleted", "Deleted"

    class Scan(models.TextChoices):
        PENDING = "pending", "Pending"
        CLEAN = "clean", "Clean"
        INFECTED = "infected", "Infected"
        UNSCANNED = "unscanned", "Unscanned"

    purpose = models.CharField(max_length=64)
    key = models.CharField(max_length=512)
    owner_type = models.CharField(max_length=64, blank=True, default="")
    owner_id = models.UUIDField(null=True, blank=True)
    original_name = models.CharField(max_length=200)
    content_type = models.CharField(max_length=100)
    declared_size = models.BigIntegerField()
    size = models.BigIntegerField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.AWAITING_UPLOAD)
    scan_state = models.CharField(max_length=16, choices=Scan.choices, default=Scan.PENDING)
    uploaded_by = models.UUIDField(null=True, blank=True)
    upload_expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "files_storedfile"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"], name="files_key_unique"),
            models.CheckConstraint(
                condition=models.Q(declared_size__gt=0), name="files_declared_size_positive"
            ),
        ]
        indexes = [models.Index(fields=["tenant", "owner_type", "owner_id"])]

    def __str__(self) -> str:
        return f"{self.purpose}:{self.pk}"
