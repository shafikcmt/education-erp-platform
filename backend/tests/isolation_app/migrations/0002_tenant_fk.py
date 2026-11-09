"""Phase 3 M2: ``TenantScopedModel.tenant`` is now a foreign key to the tenant registry.

The column (``tenant_id``) and its index already exist; only the model state changes and the
registry foreign key is added.
"""

import django.db.models.deletion
from django.db import migrations, models

from apps.core.db_operations import refuse_isolation_rollback


def _refuse(apps, schema_editor):  # type: ignore[no-untyped-def]
    refuse_isolation_rollback("probe registry foreign key")


class Migration(migrations.Migration):
    dependencies = [
        ("isolation_probe", "0001_initial"),
        ("tenancy", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name="proberecord", name="tenant_id"),
                migrations.AddField(
                    model_name="proberecord",
                    name="tenant",
                    field=models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="tenancy.tenant",
                    ),
                    preserve_default=False,
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    "ALTER TABLE isolation_probe_record ADD CONSTRAINT "
                    "isolation_probe_record_tenant_fk FOREIGN KEY (tenant_id) "
                    "REFERENCES tenancy_tenant (id) DEFERRABLE INITIALLY DEFERRED",
                    "ALTER TABLE isolation_probe_record DROP CONSTRAINT "
                    "isolation_probe_record_tenant_fk",
                )
            ],
        ),
        migrations.RunPython(migrations.RunPython.noop, _refuse),
    ]
