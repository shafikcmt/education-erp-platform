"""Narrow runtime grants on the unused Django group/permission link tables (Phase 3 M1).

Groups and Django permissions are unused (ADR-033), so the runtime role never inserts or
updates these rows. It keeps DELETE because deleting a user makes Django delete its (empty)
link rows.
"""

from django.db import migrations

from apps.core.db_operations import RestrictTableGrants


class Migration(migrations.Migration):
    dependencies = [("identity", "0002_phase2_auth"), ("core", "0004_restrict_framework_tables")]

    operations = [
        RestrictTableGrants("identity_user_groups", ("SELECT", "DELETE")),
        RestrictTableGrants("identity_user_user_permissions", ("SELECT", "DELETE")),
    ]
