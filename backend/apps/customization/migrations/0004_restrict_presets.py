"""Presets are written only by the owner-run sync: SELECT only for the runtime role."""

from django.db import migrations

from apps.core.db_operations import RestrictTableGrants


class Migration(migrations.Migration):
    dependencies = [("customization", "0003_preset")]
    operations = [RestrictTableGrants("customization_preset", ("SELECT",))]
