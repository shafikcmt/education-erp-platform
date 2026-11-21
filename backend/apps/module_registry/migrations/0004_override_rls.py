"""Self-scoped, tenant-read-only RLS on module overrides (Phase 4 M2; ADR-051, ADR-052)."""

from django.db import migrations

from apps.core.db_operations import EnableSelfScopedRLS


class Migration(migrations.Migration):
    dependencies = [("module_registry", "0003_featureflag_moduleoverride")]

    operations = [
        EnableSelfScopedRLS("module_registry_override", key="tenant_id", tenant_writes=False)
    ]
