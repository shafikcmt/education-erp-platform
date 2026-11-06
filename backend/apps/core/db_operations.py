"""Reusable migration operations for database privilege hardening.

``RestrictTableGrants`` narrows what the runtime role (``erp_app``, ADR-009) may do on a table.
The bootstrap script grants ``SELECT, INSERT, UPDATE, DELETE`` on every table by default;
append-only tables (audit log, ``django_migrations``) must be narrowed explicitly.

Migrations run as ``erp_owner``, which owns the tables and may therefore change their grants.
"""

from typing import Any

from django.conf import settings
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import ProjectState

_ALL_DML = ("SELECT", "INSERT", "UPDATE", "DELETE")
_ALLOWED = frozenset(_ALL_DML)


def app_role() -> str:
    return str(getattr(settings, "DATABASE_APP_ROLE", "erp_app"))


class RestrictTableGrants(migrations.operations.base.Operation):
    """Grant the runtime role only ``privileges`` on ``table`` (reversible).

    Reversal restores the bootstrap default (full DML), matching ``01-roles.sh``.
    """

    reversible = True
    reduces_to_sql = True

    def __init__(self, table: str, privileges: tuple[str, ...]) -> None:
        unknown = set(privileges) - _ALLOWED
        if unknown:
            raise ValueError(f"Unsupported privileges: {sorted(unknown)}")
        self.table = table
        self.privileges = tuple(privileges)

    def deconstruct(self) -> tuple[str, list[Any], dict[str, Any]]:
        return (self.__class__.__name__, [], {"table": self.table, "privileges": self.privileges})

    def state_forwards(self, app_label: str, state: ProjectState) -> None:
        """Privileges are not part of Django's model state."""

    def _apply(self, schema_editor: BaseDatabaseSchemaEditor, privileges: tuple[str, ...]) -> None:
        quote = schema_editor.quote_name
        table, role = quote(self.table), quote(app_role())
        schema_editor.execute(f"REVOKE ALL ON TABLE {table} FROM {role}")
        if privileges:
            schema_editor.execute(f"GRANT {', '.join(privileges)} ON TABLE {table} TO {role}")

    def database_forwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        self._apply(schema_editor, self.privileges)

    def database_backwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        self._apply(schema_editor, _ALL_DML)

    def describe(self) -> str:
        return f"Restrict {app_role()} to {', '.join(self.privileges) or 'nothing'} on {self.table}"


def immutable_table_sql(table: str) -> tuple[str, str]:
    """Return ``(forward_sql, reverse_sql)`` for a trigger that rejects UPDATE/DELETE/TRUNCATE.

    The trigger applies to **every** role, including the owner, so append-only data stays
    append-only even for migrations; only a reviewed migration that drops the trigger can
    change that.
    """
    fn = f"{table}_reject_mutation"
    forward = f"""
CREATE FUNCTION {fn}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only (% rejected)', TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'insufficient_privilege';
END $$;
CREATE TRIGGER {table}_immutable_rows BEFORE UPDATE OR DELETE ON {table}
  FOR EACH ROW EXECUTE FUNCTION {fn}();
CREATE TRIGGER {table}_immutable_truncate BEFORE TRUNCATE ON {table}
  FOR EACH STATEMENT EXECUTE FUNCTION {fn}();
"""
    reverse = f"""
DROP TRIGGER IF EXISTS {table}_immutable_truncate ON {table};
DROP TRIGGER IF EXISTS {table}_immutable_rows ON {table};
DROP FUNCTION IF EXISTS {fn}();
"""
    return forward, reverse


def current_db_role() -> str:
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user")
        row = cursor.fetchone()
    return str(row[0]) if row else ""


def require_owner_role(command: str) -> None:
    """Maintenance commands that rewrite protected evidence (key rotation, index rebuild) must
    run as the owner role from the ops/migrate container, never as the runtime role (L4)."""
    from django.core.management.base import CommandError

    if current_db_role() == app_role():
        raise CommandError(
            f"{command} must run as the database owner role, e.g. "
            "`docker compose run --rm --entrypoint sh migrate -c "
            f"'DATABASE_URL=$DATABASE_MIGRATION_URL python manage.py {command}'`."
        )
