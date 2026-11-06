"""Append-only security audit log (Phase 2 plan §6.8) and its encrypted IP side table (§6.9).

* ``AuditEvent`` is immutable for **every** role: the runtime role has only SELECT/INSERT, and a
  trigger rejects UPDATE/DELETE/TRUNCATE even for the owner (migration 0002).
* ``tenant_id`` is nullable: the table is **dual-scope** (§4.6). Platform events have NULL;
  Phase 3 tenant events carry their tenant under the dual-scope RLS policy.
* There is **no IP column** on the event. IPs live in ``AuditEventIP`` (encrypted, blind-indexed,
  deletable), so retention/anonymisation never needs to modify the immutable log (ADR-036).
* Actor and target are plain UUIDs, not foreign keys: the log must outlive the rows it describes.
"""

from django.db import models

from apps.core.ids import new_id


class ActorType(models.TextChoices):
    USER = "user", "User"
    SYSTEM = "system", "System"
    SUPPORT = "support", "Support session"
    AI = "ai", "AI assistant"


class Outcome(models.TextChoices):
    SUCCESS = "success", "Success"
    FAILURE = "failure", "Failure"
    DENIED = "denied", "Denied"


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    occurred_at = models.DateTimeField(db_index=True)
    tenant_id = models.UUIDField(null=True, blank=True)
    actor_user_id = models.UUIDField(null=True, blank=True)
    actor_type = models.CharField(max_length=16, choices=ActorType.choices)
    support_session_id = models.UUIDField(null=True, blank=True)
    action = models.CharField(max_length=80)
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    target_type = models.CharField(max_length=80, blank=True, default="")
    target_id = models.CharField(max_length=64, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    user_agent_summary = models.CharField(max_length=80, blank=True, default="")
    request_id = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        db_table = "audit_auditevent"
        ordering = ("-occurred_at", "-id")
        # Partition-friendly: every index leads with or includes occurred_at (Phase 18).
        indexes = [
            models.Index(fields=["tenant_id", "-occurred_at"], name="audit_evt_tenant_time"),
            models.Index(fields=["actor_user_id", "-occurred_at"], name="audit_evt_actor_time"),
            models.Index(fields=["action", "-occurred_at"], name="audit_evt_action_time"),
            models.Index(
                fields=["target_type", "target_id", "-occurred_at"], name="audit_evt_target_time"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.action} ({self.outcome})"


class AuditEventIP(models.Model):
    """Encrypted client IP of an audit event (ADR-036). Deletable/anonymisable; the event is not."""

    event = models.OneToOneField(
        AuditEvent, on_delete=models.DO_NOTHING, primary_key=True, related_name="ip"
    )
    ip_encrypted = models.BinaryField(null=True, blank=True)
    ip_index = models.CharField(max_length=64, null=True, blank=True, db_index=True)  # noqa: DJ001 - NULL = anonymised
    ip_prefix = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(db_index=True)
    anonymized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "audit_auditeventip"

    def __str__(self) -> str:
        return f"ip for {self.event_id}"
