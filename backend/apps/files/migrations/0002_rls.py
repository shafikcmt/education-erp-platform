"""Standard RLS for stored files (Phase 6 M3; ADR-064). Reversal is refused."""

from django.db import migrations

from apps.core.db_operations import EnableTenantRLS, refuse_isolation_rollback


def _refuse(apps, schema_editor):  # type: ignore[no-untyped-def]
    refuse_isolation_rollback("stored file row-level security")


class Migration(migrations.Migration):
    dependencies = [("files", "0001_initial")]
    operations = [
        EnableTenantRLS("files_storedfile"),
        migrations.RunPython(migrations.RunPython.noop, _refuse),
    ]
