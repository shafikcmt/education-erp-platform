"""Standard RLS for portal invitations (Phase 7 M8). Reversal is refused."""

from django.db import migrations

from apps.core.db_operations import EnableTenantRLS, refuse_isolation_rollback


def _refuse(apps, schema_editor):  # type: ignore[no-untyped-def]
    refuse_isolation_rollback("students portal invitation row-level security")


class Migration(migrations.Migration):
    dependencies = [("students", "0007_portalinvite")]
    operations = [
        EnableTenantRLS("students_portalinvite"),
        migrations.RunPython(migrations.RunPython.noop, _refuse),
    ]
