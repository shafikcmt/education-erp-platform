"""Composite tenant keys and standard RLS for the timetable (Phase 7 M7; ADR-071).

A period's schedule, a room's campus, and a slot's year, term, unit, period and room belong to
the slot's institution; offerings and teachers belong to the tenant (the service checks the
offering's institution and that the teacher teaches it). Reversal is refused.
"""

from django.db import migrations

from apps.core.db_operations import EnableTenantRLS, refuse_isolation_rollback

INST = "tenancy_institution (tenant_id, id)"
COMPOSITE_FKS = [
    ("timetable_bellschedule", "timetable_schedule_institution_fk", "tenant_id, institution_id",
     INST),
    ("timetable_period", "timetable_period_institution_fk", "tenant_id, institution_id", INST),
    ("timetable_period", "timetable_period_schedule_fk", "tenant_id, institution_id, schedule_id",
     "timetable_bellschedule (tenant_id, institution_id, id)"),
    ("timetable_room", "timetable_room_institution_fk", "tenant_id, institution_id", INST),
    ("timetable_room", "timetable_room_campus_fk", "tenant_id, institution_id, campus_id",
     "tenancy_campus (tenant_id, institution_id, id)"),
    ("timetable_slot", "timetable_slot_institution_fk", "tenant_id, institution_id", INST),
    ("timetable_slot", "timetable_slot_year_fk", "tenant_id, institution_id, year_id",
     "academics_academicyear (tenant_id, institution_id, id)"),
    ("timetable_slot", "timetable_slot_term_fk", "tenant_id, institution_id, term_id",
     "academics_term (tenant_id, institution_id, id)"),
    ("timetable_slot", "timetable_slot_unit_fk", "tenant_id, institution_id, unit_id",
     "academics_unit (tenant_id, institution_id, id)"),
    ("timetable_slot", "timetable_slot_period_fk", "tenant_id, institution_id, period_id",
     "timetable_period (tenant_id, institution_id, id)"),
    ("timetable_slot", "timetable_slot_room_fk", "tenant_id, institution_id, room_id",
     "timetable_room (tenant_id, institution_id, id)"),
    ("timetable_slot", "timetable_slot_offering_fk", "tenant_id, offering_id",
     "academics_offering (tenant_id, id)"),
    ("timetable_slot", "timetable_slot_teacher_fk", "tenant_id, teacher_id",
     "tenancy_membership (tenant_id, id)"),
]  # fmt: skip
TABLES = ["timetable_bellschedule", "timetable_period", "timetable_room", "timetable_slot"]


def _refuse(apps, schema_editor):  # type: ignore[no-untyped-def]
    refuse_isolation_rollback("timetable keys and row-level security")


class Migration(migrations.Migration):
    dependencies = [("timetable", "0001_initial")]
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
