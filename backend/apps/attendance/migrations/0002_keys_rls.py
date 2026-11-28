"""Composite tenant keys and standard RLS for attendance (Phase 8 M1; ADR-076).

A register's campus, year, term and unit belong to its institution; a record's register (with
the same date) and student belong to the record's institution; a staff record's and a leave
request's people belong to theirs. Offerings and memberships belong to the tenant (services
check the offering's unit). Reversal is refused.
"""

from django.db import migrations

from apps.core.db_operations import EnableTenantRLS, refuse_isolation_rollback

INST = "tenancy_institution (tenant_id, id)"
MEMBER = "tenancy_membership (tenant_id, id)"
COMPOSITE_FKS = [
    ("attendance_register", "attendance_register_institution_fk", "tenant_id, institution_id",
     INST),
    ("attendance_register", "attendance_register_campus_fk", "tenant_id, institution_id, campus_id",
     "tenancy_campus (tenant_id, institution_id, id)"),
    ("attendance_register", "attendance_register_year_fk", "tenant_id, institution_id, year_id",
     "academics_academicyear (tenant_id, institution_id, id)"),
    ("attendance_register", "attendance_register_term_fk", "tenant_id, institution_id, term_id",
     "academics_term (tenant_id, institution_id, id)"),
    ("attendance_register", "attendance_register_unit_fk", "tenant_id, institution_id, unit_id",
     "academics_unit (tenant_id, institution_id, id)"),
    ("attendance_register", "attendance_register_offering_fk", "tenant_id, offering_id",
     "academics_offering (tenant_id, id)"),
    ("attendance_register", "attendance_register_taken_by_fk", "tenant_id, taken_by_id", MEMBER),
    ("attendance_record", "attendance_record_register_fk",
     "tenant_id, institution_id, register_id, date",
     "attendance_register (tenant_id, institution_id, id, date)"),
    ("attendance_record", "attendance_record_student_fk", "tenant_id, institution_id, student_id",
     "students_student (tenant_id, institution_id, id)"),
    ("attendance_staffrecord", "attendance_staffrecord_institution_fk",
     "tenant_id, institution_id", INST),
    ("attendance_staffrecord", "attendance_staffrecord_campus_fk",
     "tenant_id, institution_id, campus_id", "tenancy_campus (tenant_id, institution_id, id)"),
    ("attendance_staffrecord", "attendance_staffrecord_staff_fk",
     "tenant_id, institution_id, staff_id", "staff_profile (tenant_id, institution_id, id)"),
    ("attendance_staffrecord", "attendance_staffrecord_marked_by_fk", "tenant_id, marked_by_id",
     MEMBER),
    ("attendance_leaverequest", "attendance_leave_institution_fk", "tenant_id, institution_id",
     INST),
    ("attendance_leaverequest", "attendance_leave_student_fk",
     "tenant_id, institution_id, student_id", "students_student (tenant_id, institution_id, id)"),
    ("attendance_leaverequest", "attendance_leave_staff_fk", "tenant_id, institution_id, staff_id",
     "staff_profile (tenant_id, institution_id, id)"),
    ("attendance_leaverequest", "attendance_leave_requested_by_fk", "tenant_id, requested_by_id",
     MEMBER),
    ("attendance_leaverequest", "attendance_leave_decided_by_fk", "tenant_id, decided_by_id",
     MEMBER),
]  # fmt: skip
TABLES = [
    "attendance_register",
    "attendance_record",
    "attendance_staffrecord",
    "attendance_leaverequest",
]


def _refuse(apps, schema_editor):  # type: ignore[no-untyped-def]
    refuse_isolation_rollback("attendance keys and row-level security")


class Migration(migrations.Migration):
    dependencies = [("attendance", "0001_initial")]
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
