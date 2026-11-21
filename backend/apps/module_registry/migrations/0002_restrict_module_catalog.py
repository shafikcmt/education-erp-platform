"""The runtime role may only read the module catalogue (Phase 4 M1; ADR-050, as O1 for
permissions). The owner-run ``sync_modules`` writes it."""

from django.db import migrations

from apps.core.db_operations import RestrictTableGrants


class Migration(migrations.Migration):
    dependencies = [("module_registry", "0001_initial")]

    operations = [RestrictTableGrants("module_registry_module", ("SELECT",))]
