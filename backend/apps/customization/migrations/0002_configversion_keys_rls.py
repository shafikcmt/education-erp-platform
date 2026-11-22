"""Composite tenant keys and standard RLS for configuration versions (Phase 5 M1).

The institution and campus references are ``(tenant_id, …)`` keys (``MATCH SIMPLE``,
``ON DELETE RESTRICT``), so a version can never point at another tenant's scope, nor at a campus
of another institution. Reversing this migration is refused (plan §19.2 of Phase 3).
"""

from django.db import migrations

from apps.core.db_operations import EnableTenantRLS, refuse_isolation_rollback

COMPOSITE_FKS = [
    ("customization_config_institution_fk", "tenant_id, institution_id",
     "tenancy_institution (tenant_id, id)"),
    ("customization_config_campus_fk", "tenant_id, institution_id, campus_id",
     "tenancy_campus (tenant_id, institution_id, id)"),
]  # fmt: skip
FK_FORWARD = [
    f"ALTER TABLE customization_configversion ADD CONSTRAINT {name} FOREIGN KEY ({cols}) "
    f"REFERENCES {ref} MATCH SIMPLE ON DELETE RESTRICT NOT DEFERRABLE"
    for name, cols, ref in COMPOSITE_FKS
]
FK_REVERSE = [
    f"ALTER TABLE customization_configversion DROP CONSTRAINT IF EXISTS {name}"
    for name, _, _ in COMPOSITE_FKS
]


def _refuse(apps, schema_editor):  # type: ignore[no-untyped-def]
    refuse_isolation_rollback("configuration version keys and row-level security")


class Migration(migrations.Migration):
    dependencies = [
        ("customization", "0001_initial"),
        ("tenancy", "0004_definer_functions"),
    ]

    operations = [
        migrations.RunSQL(FK_FORWARD, FK_REVERSE),
        EnableTenantRLS("customization_configversion"),
        migrations.RunPython(migrations.RunPython.noop, _refuse),
    ]
