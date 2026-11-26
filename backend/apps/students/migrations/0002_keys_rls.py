"""Composite tenant keys and standard RLS for students (Phase 7 M1; ADR-068).

A student and an enrollment stay in one institution: an enrollment's student, year and unit
belong to its institution; a guardian link's student and guardian, and every membership, belong
to the tenant. Reversal is refused.
"""

from django.db import migrations

from apps.core.db_operations import EnableTenantRLS, refuse_isolation_rollback

INST = "tenancy_institution (tenant_id, id)"
MEMBERSHIP = "tenancy_membership (tenant_id, id)"
COMPOSITE_FKS = [
    ("students_student", "students_student_institution_fk", "tenant_id, institution_id", INST),
    ("students_student", "students_student_membership_fk", "tenant_id, membership_id",
     MEMBERSHIP),
    ("students_guardian", "students_guardian_membership_fk", "tenant_id, membership_id",
     MEMBERSHIP),
    ("students_studentguardian", "students_link_student_fk", "tenant_id, student_id",
     "students_student (tenant_id, id)"),
    ("students_studentguardian", "students_link_guardian_fk", "tenant_id, guardian_id",
     "students_guardian (tenant_id, id)"),
    ("students_enrollment", "students_enrollment_institution_fk", "tenant_id, institution_id",
     INST),
    ("students_enrollment", "students_enrollment_student_fk",
     "tenant_id, institution_id, student_id", "students_student (tenant_id, institution_id, id)"),
    ("students_enrollment", "students_enrollment_year_fk", "tenant_id, institution_id, year_id",
     "academics_academicyear (tenant_id, institution_id, id)"),
    ("students_enrollment", "students_enrollment_unit_fk", "tenant_id, institution_id, unit_id",
     "academics_unit (tenant_id, institution_id, id)"),
]  # fmt: skip
TABLES = [
    "students_student",
    "students_guardian",
    "students_studentguardian",
    "students_enrollment",
]


def _refuse(apps, schema_editor):  # type: ignore[no-untyped-def]
    refuse_isolation_rollback("students keys and row-level security")


class Migration(migrations.Migration):
    dependencies = [("students", "0001_initial")]
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
