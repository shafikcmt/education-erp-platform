"""Narrow runtime grants on Django framework tables (Phase 3 M1, plan §5.2).

Checked before narrowing: these tables are written only by ``migrate`` (``post_migrate``
creates content types and permissions) which runs as the owner. Groups and Django
permissions are unused for authorization (ADR-033), so the runtime role needs only SELECT.
``django_session`` keeps full DML (session store).
"""

from django.db import migrations

from apps.core.db_operations import RestrictTableGrants


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_tenant_context_function"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        RestrictTableGrants("auth_group", ("SELECT",)),
        RestrictTableGrants("auth_group_permissions", ("SELECT",)),
        RestrictTableGrants("auth_permission", ("SELECT",)),
        RestrictTableGrants("django_content_type", ("SELECT",)),
    ]
