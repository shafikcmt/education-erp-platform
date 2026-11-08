"""``app_tenant_id()``: the SQL side of the transaction-local tenant context (Phase 3 M1,
ADR-009 §3/§4, ADR-042). Every tenant RLS policy compares ``tenant_id`` with it."""

from django.db import migrations

from apps.core.db_operations import InstallTenantContextFunction


class Migration(migrations.Migration):
    dependencies = [("core", "0002_restrict_django_migrations")]

    operations = [InstallTenantContextFunction()]
