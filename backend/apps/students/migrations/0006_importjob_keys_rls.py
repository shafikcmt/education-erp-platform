"""Composite tenant key and standard RLS for import jobs (Phase 7 M6). Reversal is refused."""

from django.db import migrations

from apps.core.db_operations import EnableTenantRLS, refuse_isolation_rollback


def _refuse(apps, schema_editor):  # type: ignore[no-untyped-def]
    refuse_isolation_rollback("students import job keys and row-level security")


class Migration(migrations.Migration):
    dependencies = [("students", "0005_importjob")]
    operations = [
        migrations.RunSQL(
            "ALTER TABLE students_importjob ADD CONSTRAINT students_importjob_institution_fk "
            "FOREIGN KEY (tenant_id, institution_id) REFERENCES tenancy_institution (tenant_id, id) "
            "MATCH SIMPLE ON DELETE RESTRICT NOT DEFERRABLE",
            "ALTER TABLE students_importjob DROP CONSTRAINT IF EXISTS students_importjob_institution_fk",
        ),
        EnableTenantRLS("students_importjob"),
        migrations.RunPython(migrations.RunPython.noop, _refuse),
    ]
