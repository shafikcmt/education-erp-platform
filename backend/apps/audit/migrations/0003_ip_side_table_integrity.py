"""IP side-table integrity (review L4) and audit rollback safeguard (review I1).

* ``audit_auditevent.recorded_tx_at`` is forced by trigger to ``transaction_timestamp()``.
* ``audit_auditeventip`` for the runtime role:
  - INSERT only for an event written in the **same transaction** (no IP rows for old events,
    so DELETE + INSERT can't be used to rewrite evidence);
  - UPDATE may only **clear** ``ip_encrypted``/``ip_index`` and set ``anonymized_at``
    (retention); event, prefix and creation time can't change, and values can't be replaced;
  - DELETE stays allowed (ADR-036 erasure).
  The owner role (key-rotation and index-rebuild commands, run from the ops container) may
  rewrite ciphertext and indexes.
* Reversing this migration (and therefore the earlier audit migrations) is refused unless
  ``ERP_ALLOW_AUDIT_ROLLBACK=true`` in a non-production environment.
"""

from typing import Any

from django.conf import settings
from django.db import migrations, models

from apps.core.db_operations import app_role


def _forward_sql() -> str:
    role = app_role().replace("'", "''")
    return f"""
CREATE FUNCTION audit_auditevent_stamp_tx() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.recorded_tx_at := transaction_timestamp();
  RETURN NEW;
END $$;
CREATE TRIGGER audit_auditevent_stamp_tx BEFORE INSERT ON audit_auditevent
  FOR EACH ROW EXECUTE FUNCTION audit_auditevent_stamp_tx();

CREATE FUNCTION audit_auditeventip_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF current_user <> '{role}' THEN
    RETURN NEW;  -- owner/ops maintenance (key rotation, index rebuild)
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NOT EXISTS (
      SELECT 1 FROM audit_auditevent e
      WHERE e.id = NEW.event_id AND e.recorded_tx_at = transaction_timestamp()
    ) THEN
      RAISE EXCEPTION 'audit IP rows can only be added with their event'
        USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
  END IF;
  IF NEW.event_id IS DISTINCT FROM OLD.event_id
     OR NEW.created_at IS DISTINCT FROM OLD.created_at
     OR NEW.ip_prefix IS DISTINCT FROM OLD.ip_prefix
     OR (NEW.ip_encrypted IS NOT NULL AND NEW.ip_encrypted IS DISTINCT FROM OLD.ip_encrypted)
     OR (NEW.ip_index IS NOT NULL AND NEW.ip_index IS DISTINCT FROM OLD.ip_index)
     OR (OLD.anonymized_at IS NOT NULL AND NEW.anonymized_at IS DISTINCT FROM OLD.anonymized_at)
  THEN
    RAISE EXCEPTION 'audit IP evidence can only be cleared, not rewritten'
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER audit_auditeventip_guard BEFORE INSERT OR UPDATE ON audit_auditeventip
  FOR EACH ROW EXECUTE FUNCTION audit_auditeventip_guard();
"""


REVERSE_SQL = """
DROP TRIGGER IF EXISTS audit_auditeventip_guard ON audit_auditeventip;
DROP FUNCTION IF EXISTS audit_auditeventip_guard();
DROP TRIGGER IF EXISTS audit_auditevent_stamp_tx ON audit_auditevent;
DROP FUNCTION IF EXISTS audit_auditevent_stamp_tx();
"""


def refuse_rollback(apps: Any, schema_editor: Any) -> None:
    """I1: undoing audit protection destroys the guarantee (and earlier migrations the data)."""
    allowed = getattr(settings, "ERP_ALLOW_AUDIT_ROLLBACK", False)
    environment = str(getattr(settings, "APP_ENVIRONMENT", "")).lower()
    if not allowed or environment in {"production", "prod", "staging"}:
        raise RuntimeError(
            "Refusing to reverse audit migrations: this removes audit-log protection and data. "
            "Only for disposable non-production databases with ERP_ALLOW_AUDIT_ROLLBACK=true."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0002_append_only"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditevent",
            name="recorded_tx_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.RunSQL(_forward_sql(), REVERSE_SQL),
        # Last, so that reversing starts here and is refused (I1).
        migrations.RunPython(migrations.RunPython.noop, refuse_rollback),
    ]
