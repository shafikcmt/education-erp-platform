"""Reusable migration operations for database privilege hardening and tenant isolation.

* ``RestrictTableGrants`` narrows what the runtime role (``erp_app``, ADR-009) may do on a
  table. The bootstrap script grants ``SELECT, INSERT, UPDATE, DELETE`` on every table by
  default; append-only tables (audit log, ``django_migrations``) must be narrowed explicitly.
* ``InstallTenantContextFunction`` creates ``app_tenant_id()`` (Phase 3 M1).
* ``EnableTenantRLS`` / ``EnableDualScopeRLS`` enable **and force** Row-Level Security with
  explicit per-command policies named ``tenant_isolation_<command>`` (ADR-046).

Migrations run as ``erp_owner``, which owns the tables and may therefore change their grants
and policies. Reversing a tenant-isolation operation is refused in production and staging and
needs ``ERP_ALLOW_ISOLATION_ROLLBACK=true`` elsewhere (plan §19.2).
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


# --------------------------------------------------------------------------- tenant isolation
TENANT_CONTEXT_EXPR = "(SELECT public.app_tenant_id())"
POLICY_COMMANDS = ("select", "insert", "update", "delete")

# ``app_tenant_id()`` reads the transaction-local setting written by ``tenant_atomic``. A
# missing, empty or malformed value yields NULL, and ``tenant_id = NULL`` is never true, so
# every policy fails closed. Plain SQL (no SECURITY DEFINER, no SET clause) so the planner can
# inline it; schema-qualified calls make it independent of ``search_path``.
APP_TENANT_ID_SQL = """
CREATE FUNCTION public.app_tenant_id() RETURNS uuid
LANGUAGE sql STABLE PARALLEL SAFE AS $$
  SELECT CASE
    WHEN s ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN s::uuid
  END
  FROM (SELECT pg_catalog.current_setting('app.tenant_id', true) AS s) AS setting
$$;
"""


def refuse_isolation_rollback(what: str) -> None:
    """Plan §19.2 / ADR-046: never in production or staging; elsewhere only when allowed."""
    allowed = getattr(settings, "ERP_ALLOW_ISOLATION_ROLLBACK", False)
    environment = str(getattr(settings, "APP_ENVIRONMENT", "")).lower()
    if not allowed or environment in {"production", "prod", "staging"}:
        raise RuntimeError(
            f"Refusing to reverse {what}: this removes tenant isolation. Only for disposable "
            "non-production databases with ERP_ALLOW_ISOLATION_ROLLBACK=true."
        )


class InstallTenantContextFunction(migrations.operations.base.Operation):
    """Create ``public.app_tenant_id()``; ``EXECUTE`` only for the owner and the runtime role."""

    reversible = True
    reduces_to_sql = True

    def deconstruct(self) -> tuple[str, list[Any], dict[str, Any]]:
        return (self.__class__.__name__, [], {})

    def state_forwards(self, app_label: str, state: ProjectState) -> None:
        """Functions are not part of Django's model state."""

    def database_forwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        role = schema_editor.quote_name(app_role())
        schema_editor.execute(APP_TENANT_ID_SQL)
        schema_editor.execute("REVOKE ALL ON FUNCTION public.app_tenant_id() FROM PUBLIC")
        schema_editor.execute(f"GRANT EXECUTE ON FUNCTION public.app_tenant_id() TO {role}")

    def database_backwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        refuse_isolation_rollback("the tenant context function")
        # No CASCADE: dropping fails while any policy still uses the function.
        schema_editor.execute("DROP FUNCTION public.app_tenant_id()")

    def describe(self) -> str:
        return "Install app_tenant_id() (transaction-local tenant context)"


def tenant_policy_expressions(kind: str) -> dict[str, tuple[str | None, str | None]]:
    """``{command: (USING, WITH CHECK)}`` for a policy class (plan §5.1).

    * ``standard``: ``tenant_id = ctx``.
    * ``dual``: reads see platform rows (``tenant_id IS NULL``) and the tenant's rows; writes
      only rows of the current scope (``IS NOT DISTINCT FROM``: platform context writes
      platform rows, tenant context its own rows).
    * ``dual_private``: reads and writes only the current scope.
    """
    ctx = TENANT_CONTEXT_EXPR
    if kind == "standard":
        own = f"(tenant_id = {ctx})"
        read = own
    elif kind in {"dual", "dual_private"}:
        own = f"(tenant_id IS NOT DISTINCT FROM {ctx})"
        read = f"(tenant_id IS NULL OR tenant_id = {ctx})" if kind == "dual" else own
    else:
        raise ValueError(f"Unknown policy kind {kind!r}")
    return {
        "select": (read, None),
        "insert": (None, own),
        "update": (own, own),
        "delete": (own, None),
    }


def policy_name(command: str) -> str:
    return f"tenant_isolation_{command}"


class _EnableRLS(migrations.operations.base.Operation):
    reversible = True
    reduces_to_sql = True
    kind = "standard"

    def __init__(self, table: str) -> None:
        self.table = table

    def deconstruct(self) -> tuple[str, list[Any], dict[str, Any]]:
        return (self.__class__.__name__, [], {"table": self.table})

    def state_forwards(self, app_label: str, state: ProjectState) -> None:
        """Policies are not part of Django's model state."""

    def database_forwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        table = schema_editor.quote_name(self.table)
        schema_editor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        for command, (using, check) in tenant_policy_expressions(self.kind).items():
            sql = f"CREATE POLICY {policy_name(command)} ON {table} FOR {command.upper()}"
            if using:
                sql += f" USING {using}"
            if check:
                sql += f" WITH CHECK {check}"
            schema_editor.execute(sql)

    def database_backwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        refuse_isolation_rollback(f"row-level security on {self.table}")
        table = schema_editor.quote_name(self.table)
        for command in POLICY_COMMANDS:
            schema_editor.execute(f"DROP POLICY IF EXISTS {policy_name(command)} ON {table}")
        schema_editor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


class EnableTenantRLS(_EnableRLS):
    """ENABLE + FORCE RLS with ``tenant_id = app_tenant_id()`` policies (ADR-009 §3)."""

    kind = "standard"

    def describe(self) -> str:
        return f"Enable tenant RLS on {self.table}"


class EnableDualScopeRLS(_EnableRLS):
    """ENABLE + FORCE RLS for a table holding platform rows (``tenant_id IS NULL``) and tenant
    rows; ``private=True`` hides platform rows from tenants and vice versa (ADR-046)."""

    def __init__(self, table: str, private: bool = False) -> None:
        super().__init__(table)
        self.private = private
        self.kind = "dual_private" if private else "dual"

    def deconstruct(self) -> tuple[str, list[Any], dict[str, Any]]:
        return (self.__class__.__name__, [], {"table": self.table, "private": self.private})

    def describe(self) -> str:
        scope = "private dual-scope" if self.private else "dual-scope"
        return f"Enable {scope} RLS on {self.table}"
