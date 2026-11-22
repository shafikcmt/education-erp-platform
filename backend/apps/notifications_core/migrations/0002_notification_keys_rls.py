"""Composite tenant key and standard RLS for notifications (Phase 5 M4)."""

from django.db import migrations

from apps.core.db_operations import EnableTenantRLS, refuse_isolation_rollback


def _refuse(apps, schema_editor):  # type: ignore[no-untyped-def]
    refuse_isolation_rollback("notification keys and row-level security")


class Migration(migrations.Migration):
    dependencies = [("notifications_core", "0001_initial"), ("tenancy", "0004_definer_functions")]
    operations = [
        migrations.RunSQL(
            "ALTER TABLE notifications_core_notification ADD CONSTRAINT notif_membership_fk "
            "FOREIGN KEY (tenant_id, membership_id) REFERENCES tenancy_membership (tenant_id, id) "
            "MATCH SIMPLE ON DELETE RESTRICT NOT DEFERRABLE",
            "ALTER TABLE notifications_core_notification DROP CONSTRAINT IF EXISTS notif_membership_fk",
        ),
        EnableTenantRLS("notifications_core_notification"),
        migrations.RunPython(migrations.RunPython.noop, _refuse),
    ]
