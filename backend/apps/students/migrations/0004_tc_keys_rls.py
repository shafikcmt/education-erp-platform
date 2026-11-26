"""Composite tenant keys and standard RLS for transfer certificates (Phase 7 M5).

A certificate's student belongs to its institution. Reversal is refused.
"""

from django.db import migrations

from apps.core.db_operations import EnableTenantRLS, refuse_isolation_rollback

COMPOSITE_FKS = [
    ("students_transfercertificate", "students_tc_institution_fk", "tenant_id, institution_id",
     "tenancy_institution (tenant_id, id)"),
    ("students_transfercertificate", "students_tc_student_fk",
     "tenant_id, institution_id, student_id", "students_student (tenant_id, institution_id, id)"),
]  # fmt: skip


def _refuse(apps, schema_editor):  # type: ignore[no-untyped-def]
    refuse_isolation_rollback("students transfer certificate keys and row-level security")


class Migration(migrations.Migration):
    dependencies = [("students", "0003_transfercertificate")]
    operations = [
        migrations.RunSQL(
            [
                f"ALTER TABLE {table} ADD CONSTRAINT {name} FOREIGN KEY ({cols}) REFERENCES {ref} "
                "MATCH SIMPLE ON DELETE RESTRICT NOT DEFERRABLE"
                for table, name, cols, ref in COMPOSITE_FKS
            ],
            [
                f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}"
                for table, name, _, _ in COMPOSITE_FKS
            ],
        ),
        EnableTenantRLS("students_transfercertificate"),
        migrations.RunPython(migrations.RunPython.noop, _refuse),
    ]
