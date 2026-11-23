"""Composite tenant keys and standard RLS for admissions (Phase 6 M4; ADR-065).

A cycle's year, a target's cycle and unit, and an application's cycle stay in one institution;
an application's target belongs to its cycle. Reversal is refused.
"""

from django.db import migrations

from apps.core.db_operations import EnableTenantRLS, refuse_isolation_rollback

INST = "tenancy_institution (tenant_id, id)"
COMPOSITE_FKS = [
    ("admissions_inquiry", "admissions_inquiry_institution_fk", "tenant_id, institution_id", INST),
    ("admissions_inquiry", "admissions_inquiry_assignee_fk", "tenant_id, assigned_to_id",
     "tenancy_membership (tenant_id, id)"),
    ("admissions_cycle", "admissions_cycle_institution_fk", "tenant_id, institution_id", INST),
    ("admissions_cycle", "admissions_cycle_year_fk", "tenant_id, institution_id, year_id",
     "academics_academicyear (tenant_id, institution_id, id)"),
    ("admissions_cycletarget", "admissions_target_institution_fk", "tenant_id, institution_id",
     INST),
    ("admissions_cycletarget", "admissions_target_cycle_fk", "tenant_id, institution_id, cycle_id",
     "admissions_cycle (tenant_id, institution_id, id)"),
    ("admissions_cycletarget", "admissions_target_unit_fk", "tenant_id, institution_id, unit_id",
     "academics_unit (tenant_id, institution_id, id)"),
    ("admissions_application", "admissions_application_institution_fk",
     "tenant_id, institution_id", INST),
    ("admissions_application", "admissions_application_cycle_fk",
     "tenant_id, institution_id, cycle_id", "admissions_cycle (tenant_id, institution_id, id)"),
    ("admissions_application", "admissions_application_target_fk", "tenant_id, cycle_id, target_id",
     "admissions_cycletarget (tenant_id, cycle_id, id)"),
]  # fmt: skip
TABLES = [
    "admissions_inquiry",
    "admissions_cycle",
    "admissions_cycletarget",
    "admissions_application",
]


def _refuse(apps, schema_editor):  # type: ignore[no-untyped-def]
    refuse_isolation_rollback("admissions keys and row-level security")


class Migration(migrations.Migration):
    dependencies = [("admissions", "0001_initial")]
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
