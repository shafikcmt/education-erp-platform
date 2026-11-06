"""Make ``django_migrations`` read-only for the runtime role (Phase 2 plan §6.8).

Only the owner role (which runs migrations) records applied migrations. The runtime role
``erp_app`` can still read the table (Django checks for unapplied migrations), but can no
longer forge or delete migration history. Closes a Phase 1 gap.
"""

from django.db import migrations

from apps.core.db_operations import RestrictTableGrants


class Migration(migrations.Migration):
    dependencies = [("core", "0001_postgres_extensions")]

    operations = [RestrictTableGrants("django_migrations", ("SELECT",))]
