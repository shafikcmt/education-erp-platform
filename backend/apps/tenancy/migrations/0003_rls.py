"""Row-level security for the tenancy tables (Phase 3 M2; plan §5.1; ADR-046).

Standard tenant policies on every tenant-owned table; self-scoping policy on the registry
(``tenancy_tenant``). Reversal is refused in production/staging (operations' own guard).
"""

from django.db import migrations

from apps.core.db_operations import EnableSelfScopedRLS, EnableTenantRLS

TENANT_TABLES = (
    "tenancy_tenantdomain",
    "tenancy_institution",
    "tenancy_campus",
    "tenancy_membership",
    "tenancy_invitation",
    "tenancy_supportsession",
)


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0002_constraints"),
        ("core", "0003_tenant_context_function"),
    ]

    operations = [
        EnableSelfScopedRLS("tenancy_tenant"),
        *(EnableTenantRLS(table) for table in TENANT_TABLES),
    ]
