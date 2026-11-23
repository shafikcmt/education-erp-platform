"""Composite tenant keys and standard RLS for admission tests and merit lists (Phase 6 M6).

A test belongs to a cycle of its institution; an assignment's test and application belong to
the same cycle; a merit list's target belongs to its cycle. Reversal is refused.
"""

from django.db import migrations

from apps.core.db_operations import EnableTenantRLS, refuse_isolation_rollback

INST = "tenancy_institution (tenant_id, id)"
CYCLE = "admissions_cycle (tenant_id, institution_id, id)"
COMPOSITE_FKS = [
    ("admissions_test", "admissions_test_institution_fk", "tenant_id, institution_id", INST),
    ("admissions_test", "admissions_test_cycle_fk", "tenant_id, institution_id, cycle_id", CYCLE),
    ("admissions_testassignment", "admissions_assignment_test_fk", "tenant_id, cycle_id, test_id",
     "admissions_test (tenant_id, cycle_id, id)"),
    ("admissions_testassignment", "admissions_assignment_application_fk",
     "tenant_id, cycle_id, application_id", "admissions_application (tenant_id, cycle_id, id)"),
    ("admissions_meritlist", "admissions_meritlist_institution_fk", "tenant_id, institution_id",
     INST),
    ("admissions_meritlist", "admissions_meritlist_cycle_fk",
     "tenant_id, institution_id, cycle_id", CYCLE),
    ("admissions_meritlist", "admissions_meritlist_target_fk", "tenant_id, cycle_id, target_id",
     "admissions_cycletarget (tenant_id, cycle_id, id)"),
]  # fmt: skip
TABLES = ["admissions_test", "admissions_testassignment", "admissions_meritlist"]


def _refuse(apps, schema_editor):  # type: ignore[no-untyped-def]
    refuse_isolation_rollback("admissions test and merit keys and row-level security")


class Migration(migrations.Migration):
    dependencies = [("admissions", "0004_tests_and_merit")]
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
