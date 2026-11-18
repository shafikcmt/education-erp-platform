"""Tenant scope for the audit log (Phase 3 M6; plan §5.1, §19.1 #8; ADR-046, D3).

* ``audit_auditeventip.tenant_id``: a copy of its event's tenant, set by trigger on insert and
  frozen afterwards, so the side table can carry the same policies as the events. Existing
  rows are backfilled before row-level security is switched on.
* ``audit_auditevent`` and ``audit_auditeventip`` get **private** dual-scope RLS: platform
  events (``tenant_id`` NULL) are visible only without a tenant context, and a tenant's
  events only inside that tenant's transaction. Platform staff can't browse tenant audit
  events from the platform host (D3); tenants never see platform events or each other's.
* Grants, the append-only trigger and the IP-integrity guard are unchanged.
"""

from typing import Any

from django.db import migrations, models

from apps.core.db_operations import EnableDualScopeRLS, refuse_isolation_rollback

SYNC_FORWARD = """
CREATE FUNCTION audit_auditeventip_tenant_sync() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    NEW.tenant_id := OLD.tenant_id;  -- never moves between scopes
    RETURN NEW;
  END IF;
  SELECT e.tenant_id INTO NEW.tenant_id FROM audit_auditevent e WHERE e.id = NEW.event_id;
  RETURN NEW;
END $$;
CREATE TRIGGER audit_auditeventip_tenant_sync BEFORE INSERT OR UPDATE ON audit_auditeventip
  FOR EACH ROW EXECUTE FUNCTION audit_auditeventip_tenant_sync();
"""
SYNC_REVERSE = """
DROP TRIGGER IF EXISTS audit_auditeventip_tenant_sync ON audit_auditeventip;
DROP FUNCTION IF EXISTS audit_auditeventip_tenant_sync();
"""
BACKFILL = """
UPDATE audit_auditeventip AS ip SET tenant_id = e.tenant_id
FROM audit_auditevent AS e
WHERE e.id = ip.event_id AND e.tenant_id IS NOT NULL AND ip.tenant_id IS NULL;
"""


def _refuse(apps: Any, schema_editor: Any) -> None:
    refuse_isolation_rollback("audit log row-level security")


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0003_ip_side_table_integrity"),
        ("core", "0003_tenant_context_function"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditeventip",
            name="tenant_id",
            field=models.UUIDField(blank=True, db_index=True, editable=False, null=True),
        ),
        migrations.RunSQL(SYNC_FORWARD, SYNC_REVERSE),
        migrations.RunSQL(BACKFILL, migrations.RunSQL.noop),
        EnableDualScopeRLS("audit_auditevent", private=True),
        EnableDualScopeRLS("audit_auditeventip", private=True),
        # Last, so that reversing starts here and is refused (plan §19.2).
        migrations.RunPython(migrations.RunPython.noop, _refuse),
    ]
