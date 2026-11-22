"""In-app notifications (Phase 5 M4; ADR-059).

One row per recipient member. Tenant-owned (standard RLS); the membership reference is a
composite ``(tenant_id, membership_id)`` key (``notifications_core.0002``). Titles and bodies are
written by platform code (never tenant templates in Phase 5) and hold no secrets.
"""

from __future__ import annotations

from django.db import models

from apps.core.tenancy.models import TenantScopedModel


class Notification(TenantScopedModel):
    membership = models.ForeignKey(
        "tenancy.Membership", on_delete=models.PROTECT, related_name="+", db_constraint=False
    )
    kind = models.CharField(max_length=64)
    title = models.CharField(max_length=200)
    body = models.CharField(max_length=1000, blank=True, default="")
    link = models.CharField(max_length=300, blank=True, default="")
    read_at = models.DateTimeField(null=True, blank=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "notifications_core_notification"
        indexes = [models.Index(fields=["tenant", "membership", "read_at"], name="notif_inbox_idx")]

    def __str__(self) -> str:
        return f"notification {self.kind}"
