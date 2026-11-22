"""Composite tenant key and standard RLS for templates and numbering (Phase 5 M5)."""

from django.db import migrations

from apps.core.db_operations import EnableTenantRLS, refuse_isolation_rollback


def _refuse(apps, schema_editor):  # type: ignore[no-untyped-def]
    refuse_isolation_rollback("template and numbering keys and row-level security")


class Migration(migrations.Migration):
    dependencies = [("customization", "0009_templates_numbering")]
    operations = [
        migrations.RunSQL(
            "ALTER TABLE customization_numbercounter ADD CONSTRAINT customization_counter_sequence_fk "
            "FOREIGN KEY (tenant_id, sequence_id) REFERENCES customization_numberingsequence "
            "(tenant_id, id) MATCH SIMPLE ON DELETE RESTRICT NOT DEFERRABLE",
            "ALTER TABLE customization_numbercounter "
            "DROP CONSTRAINT IF EXISTS customization_counter_sequence_fk",
        ),
        EnableTenantRLS("customization_templatedefinition"),
        EnableTenantRLS("customization_numberingsequence"),
        EnableTenantRLS("customization_numbercounter"),
        migrations.RunPython(migrations.RunPython.noop, _refuse),
    ]
