"""Composite keys and standard RLS for absence alerts and flags (Phase 8 M5). Reversal is
refused."""

from django.db import migrations

from apps.core.db_operations import EnableTenantRLS, refuse_isolation_rollback

INST = "tenancy_institution (tenant_id, id)"
STUDENT = "students_student (tenant_id, institution_id, id)"
COMPOSITE_FKS = [
    ("attendance_absencealert", "attendance_alert_institution_fk", "tenant_id, institution_id",
     INST),
    ("attendance_absencealert", "attendance_alert_student_fk",
     "tenant_id, institution_id, student_id", STUDENT),
    ("attendance_studentflag", "attendance_flag_institution_fk", "tenant_id, institution_id",
     INST),
    ("attendance_studentflag", "attendance_flag_student_fk",
     "tenant_id, institution_id, student_id", STUDENT),
    ("attendance_studentflag", "attendance_flag_year_fk", "tenant_id, institution_id, year_id",
     "academics_academicyear (tenant_id, institution_id, id)"),
]  # fmt: skip
TABLES = ["attendance_absencealert", "attendance_studentflag"]


def _refuse(apps, schema_editor):  # type: ignore[no-untyped-def]
    refuse_isolation_rollback("attendance alert and flag keys and row-level security")


class Migration(migrations.Migration):
    dependencies = [("attendance", "0004_alerts_flags")]
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
        *[EnableTenantRLS(table) for table in TABLES],
        migrations.RunPython(migrations.RunPython.noop, _refuse),
    ]
