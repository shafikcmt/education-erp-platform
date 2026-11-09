"""The runtime role may only read the permission catalogue (Phase 3 M1, owner decision O1).

``rbac_permission`` is written exclusively by the owner-run bootstrap (``seed_roles`` /
``sync_permissions`` in the ``migrate`` step). Reversal restores the bootstrap default DML.
"""

from django.db import migrations

from apps.core.db_operations import RestrictTableGrants


class Migration(migrations.Migration):
    dependencies = [("rbac", "0002_dual_scope_triggers")]

    operations = [RestrictTableGrants("rbac_permission", ("SELECT",))]
