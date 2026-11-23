"""Composite tenant keys and standard RLS for the academic structure (Phase 6 M1; ADR-063).

Every reference carries ``tenant_id`` and, where the target is institution-bound, the
``institution_id`` too, so a row can point neither into another tenant nor into another
institution of the same tenant: a unit's parent, campus, an offering's year, term (of that
year), unit and subject. Reversal is refused.
"""

from django.db import migrations

from apps.core.db_operations import EnableTenantRLS, refuse_isolation_rollback

INST = "tenancy_institution (tenant_id, id)"
COMPOSITE_FKS = [
    ("academics_academicyear", "academics_year_institution_fk", "tenant_id, institution_id", INST),
    ("academics_term", "academics_term_institution_fk", "tenant_id, institution_id", INST),
    ("academics_term", "academics_term_year_fk", "tenant_id, institution_id, year_id",
     "academics_academicyear (tenant_id, institution_id, id)"),
    ("academics_unit", "academics_unit_institution_fk", "tenant_id, institution_id", INST),
    ("academics_unit", "academics_unit_campus_fk", "tenant_id, institution_id, campus_id",
     "tenancy_campus (tenant_id, institution_id, id)"),
    ("academics_unit", "academics_unit_parent_fk", "tenant_id, institution_id, parent_id",
     "academics_unit (tenant_id, institution_id, id)"),
    ("academics_subject", "academics_subject_institution_fk", "tenant_id, institution_id", INST),
    ("academics_offering", "academics_offering_institution_fk", "tenant_id, institution_id", INST),
    ("academics_offering", "academics_offering_year_fk", "tenant_id, institution_id, year_id",
     "academics_academicyear (tenant_id, institution_id, id)"),
    ("academics_offering", "academics_offering_term_fk", "tenant_id, year_id, term_id",
     "academics_term (tenant_id, year_id, id)"),
    ("academics_offering", "academics_offering_unit_fk", "tenant_id, institution_id, unit_id",
     "academics_unit (tenant_id, institution_id, id)"),
    ("academics_offering", "academics_offering_subject_fk", "tenant_id, institution_id, subject_id",
     "academics_subject (tenant_id, institution_id, id)"),
    ("academics_offeringteacher", "academics_teacher_offering_fk", "tenant_id, offering_id",
     "academics_offering (tenant_id, id)"),
    ("academics_offeringteacher", "academics_teacher_membership_fk", "tenant_id, membership_id",
     "tenancy_membership (tenant_id, id)"),
]  # fmt: skip
TABLES = [
    "academics_academicyear",
    "academics_term",
    "academics_unit",
    "academics_subject",
    "academics_offering",
    "academics_offeringteacher",
]


def _refuse(apps, schema_editor):  # type: ignore[no-untyped-def]
    refuse_isolation_rollback("academic structure keys and row-level security")


class Migration(migrations.Migration):
    dependencies = [("academics", "0001_initial"), ("tenancy", "0008_invitation_recheck_inviter")]
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
