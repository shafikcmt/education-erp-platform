"""Dual-scope RLS for roles (Phase 3 M6; plan §5.1, §19.1 #7; ADR-046).

``rbac_role`` and ``rbac_rolepermission`` hold platform rows (platform roles and the tenant
role templates, ``tenant_id`` NULL) and tenant rows (each tenant's system copies and custom
roles). Every context reads the platform rows (templates are needed to sync system copies);
a tenant context also reads its own rows and nothing else. Writes are limited to the current
scope: the platform context can't modify tenant roles, and a tenant can't modify templates or
another tenant's roles. ``rbac_rolepermission.tenant_id`` is already kept equal to its role's
by the Phase 2 trigger, so no backfill is needed.
"""

from typing import Any

from django.db import migrations

from apps.core.db_operations import EnableDualScopeRLS, refuse_isolation_rollback


def _refuse(apps: Any, schema_editor: Any) -> None:
    refuse_isolation_rollback("role row-level security")


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0006_permission_support_readable"),
        ("core", "0003_tenant_context_function"),
    ]

    operations = [
        EnableDualScopeRLS("rbac_role"),
        EnableDualScopeRLS("rbac_rolepermission"),
        migrations.RunPython(migrations.RunPython.noop, _refuse),
    ]
