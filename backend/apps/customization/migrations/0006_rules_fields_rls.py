"""Standard tenant RLS for rule and custom field definitions (Phase 5 M3; ADR-046)."""

from django.db import migrations

from apps.core.db_operations import EnableTenantRLS


class Migration(migrations.Migration):
    dependencies = [("customization", "0005_rules_fields")]
    operations = [
        EnableTenantRLS("customization_ruledefinition"),
        EnableTenantRLS("customization_fielddefinition"),
    ]
