"""Standard tenant RLS on the entitlement snapshot (Phase 4 M3; ADR-052)."""

from django.db import migrations

from apps.core.db_operations import EnableTenantRLS


class Migration(migrations.Migration):
    dependencies = [("module_registry", "0005_tenantmodule")]

    operations = [EnableTenantRLS("module_registry_tenantmodule")]
