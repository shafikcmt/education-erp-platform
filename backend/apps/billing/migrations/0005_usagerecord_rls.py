"""Standard tenant RLS on usage records (Phase 4 M7; ADR-046)."""

from django.db import migrations

from apps.core.db_operations import EnableTenantRLS


class Migration(migrations.Migration):
    dependencies = [("billing", "0004_usagerecord")]
    operations = [EnableTenantRLS("billing_usagerecord")]
