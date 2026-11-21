"""Self-scoped, tenant-read-only RLS on per-tenant billing rows (Phase 4 M2; ADR-051).

A tenant context sees only its own subscription and items and can't write them; the platform
(no context) writes through platform operation P18. Reversal is refused in production.
"""

from django.db import migrations

from apps.core.db_operations import EnableSelfScopedRLS


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]

    operations = [
        EnableSelfScopedRLS("billing_subscription", key="tenant_id", tenant_writes=False),
        EnableSelfScopedRLS("billing_subscriptionitem", key="tenant_id", tenant_writes=False),
    ]
