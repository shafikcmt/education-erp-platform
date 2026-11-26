"""Composite tenant keys and standard RLS for staff (Phase 7 M3; ADR-070).

A profile, its campus, department and designation, and a department's parent stay in one
institution; an advisor's year, unit and staff profile belong to the advisor row's institution;
every membership belongs to the tenant. Reversal is refused.
"""

from django.db import migrations

from apps.core.db_operations import EnableTenantRLS, refuse_isolation_rollback

INST = "tenancy_institution (tenant_id, id)"
COMPOSITE_FKS = [
    ("staff_department", "staff_department_institution_fk", "tenant_id, institution_id", INST),
    ("staff_department", "staff_department_parent_fk", "tenant_id, institution_id, parent_id",
     "staff_department (tenant_id, institution_id, id)"),
    ("staff_designation", "staff_designation_institution_fk", "tenant_id, institution_id", INST),
    ("staff_profile", "staff_profile_institution_fk", "tenant_id, institution_id", INST),
    ("staff_profile", "staff_profile_campus_fk", "tenant_id, institution_id, campus_id",
     "tenancy_campus (tenant_id, institution_id, id)"),
    ("staff_profile", "staff_profile_department_fk", "tenant_id, institution_id, department_id",
     "staff_department (tenant_id, institution_id, id)"),
    ("staff_profile", "staff_profile_designation_fk",
     "tenant_id, institution_id, designation_id",
     "staff_designation (tenant_id, institution_id, id)"),
    ("staff_profile", "staff_profile_membership_fk", "tenant_id, membership_id",
     "tenancy_membership (tenant_id, id)"),
    ("staff_unitadvisor", "staff_advisor_institution_fk", "tenant_id, institution_id", INST),
    ("staff_unitadvisor", "staff_advisor_year_fk", "tenant_id, institution_id, year_id",
     "academics_academicyear (tenant_id, institution_id, id)"),
    ("staff_unitadvisor", "staff_advisor_unit_fk", "tenant_id, institution_id, unit_id",
     "academics_unit (tenant_id, institution_id, id)"),
    ("staff_unitadvisor", "staff_advisor_staff_fk", "tenant_id, institution_id, staff_id",
     "staff_profile (tenant_id, institution_id, id)"),
]  # fmt: skip
TABLES = ["staff_department", "staff_designation", "staff_profile", "staff_unitadvisor"]


def _refuse(apps, schema_editor):  # type: ignore[no-untyped-def]
    refuse_isolation_rollback("staff keys and row-level security")


class Migration(migrations.Migration):
    dependencies = [("staff", "0001_initial")]
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
