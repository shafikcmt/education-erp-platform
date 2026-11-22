"""Composite tenant keys and standard RLS for forms and workflows (Phase 5 M4).

A workflow instance references its (pinned) definition, and a step its instance, through
``(tenant_id, …)`` keys, so no row can point into another tenant. Reversal is refused.
"""

from django.db import migrations

from apps.core.db_operations import EnableTenantRLS, refuse_isolation_rollback

COMPOSITE_FKS = [
    ("customization_workflowinstance", "customization_wfi_definition_fk",
     "tenant_id, definition_id", "customization_workflowdefinition (tenant_id, id)"),
    ("customization_workflowstep", "customization_wfs_instance_fk",
     "tenant_id, instance_id", "customization_workflowinstance (tenant_id, id)"),
]  # fmt: skip
TABLES = [
    "customization_formdefinition",
    "customization_workflowdefinition",
    "customization_workflowinstance",
    "customization_workflowstep",
]


def _refuse(apps, schema_editor):  # type: ignore[no-untyped-def]
    refuse_isolation_rollback("form and workflow keys and row-level security")


class Migration(migrations.Migration):
    dependencies = [("customization", "0007_forms_workflows")]
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
