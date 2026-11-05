"""Abstract base models shared by every module.

Phase 1 defines only ``BaseModel``. ``TenantScopedModel`` / ``InstitutionScopedModel`` /
``CampusScopedModel`` (fail-closed tenant manager + RLS) are delivered in Phase 3 (ADR-009).
"""

from django.db import models

from apps.core.ids import new_id


class BaseModel(models.Model):
    """UUIDv7 primary key plus creation/update timestamps (stored in UTC)."""

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ("-created_at",)
