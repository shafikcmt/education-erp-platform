"""Make the audit log append-only (Phase 2 plan §6.8).

* ``erp_app`` gets only SELECT and INSERT on ``audit_auditevent``.
* A trigger rejects UPDATE/DELETE/TRUNCATE for **every** role, including the owner, so only a
  reviewed migration that drops the trigger can alter history.
* ``audit_auditeventip`` keeps full DML: IPs must be anonymisable and erasable (ADR-036).
"""

from django.db import migrations

from apps.core.db_operations import RestrictTableGrants, immutable_table_sql

_FORWARD, _REVERSE = immutable_table_sql("audit_auditevent")


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [
        RestrictTableGrants("audit_auditevent", ("SELECT", "INSERT")),
        migrations.RunSQL(_FORWARD, _REVERSE),
    ]
