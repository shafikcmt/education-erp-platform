"""RLS migration tooling and ``app_tenant_id()`` (Phase 3 M1; plan §5.1, §5.3, §19.2)."""

from typing import Any

import pytest
from django.db import DatabaseError, connection, transaction

from apps.core.db_operations import (
    EnableDualScopeRLS,
    EnableTenantRLS,
    InstallTenantContextFunction,
    refuse_isolation_rollback,
    tenant_policy_expressions,
)
from apps.core.ids import new_id
from apps.core.tenancy import tenant_atomic

pytestmark = pytest.mark.django_db


def _scalar(sql: str, params: list[Any] | None = None) -> Any:
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return cursor.fetchone()[0]


class _RecordingEditor:
    """Stands in for a schema editor: records SQL instead of executing it."""

    def __init__(self) -> None:
        self.sql: list[str] = []

    def quote_name(self, name: str) -> str:
        return f'"{name}"'

    def execute(self, sql: str, params: Any = None) -> None:
        self.sql.append(sql)


# --------------------------------------------------------------------------- app_tenant_id()
@pytest.mark.parametrize(
    ("value", "expected_null"),
    [
        ("", True),
        ("not-a-uuid", True),
        ("01ABCDEF-0000-7000-8000-000000000000", True),
        (None, False),
    ],
)
def test_app_tenant_id_fails_closed_on_missing_or_malformed_settings(value, expected_null):
    with transaction.atomic():
        if value is None:
            tid = new_id()
            _scalar("SELECT set_config('app.tenant_id', %s, true)", [str(tid)])
            assert _scalar("SELECT app_tenant_id()") == tid
        else:
            _scalar("SELECT set_config('app.tenant_id', %s, true)", [value])
            assert (_scalar("SELECT app_tenant_id()") is None) is expected_null


def test_app_tenant_id_is_null_without_any_setting():
    assert _scalar("SELECT app_tenant_id()") is None


# --------------------------------------------------------------------------- probe behaviour
def _insert(table: str, tenant_id: Any, name: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {table} (id, created_at, updated_at, tenant_id, name) "
            "VALUES (%s, now(), now(), %s, %s)",
            [new_id(), tenant_id, name],
        )


def _names(table: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT name FROM {table}")
        return {row[0] for row in cursor.fetchall()}


def _denied(fn: Any) -> bool:
    try:
        with transaction.atomic():
            fn()
    except DatabaseError as exc:
        return "row-level security" in str(exc)
    return False


def test_standard_table_without_context_shows_and_accepts_nothing(tenant_factory):
    tid = tenant_factory().id
    with tenant_atomic(tid):
        _insert("isolation_probe_record", tid, "a")
    assert _names("isolation_probe_record") == set()
    assert _denied(lambda: _insert("isolation_probe_record", tid, "x"))


def test_dual_scope_shares_platform_rows_but_isolates_tenant_writes():
    a, b = new_id(), new_id()
    _insert("isolation_probe_dual", None, "platform")  # platform context writes platform rows
    with tenant_atomic(a):
        _insert("isolation_probe_dual", a, "a-row")
        assert _names("isolation_probe_dual") == {"platform", "a-row"}
        assert _denied(lambda: _insert("isolation_probe_dual", None, "forged-platform"))
        assert _denied(lambda: _insert("isolation_probe_dual", b, "forged-b"))
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE isolation_probe_dual SET name = 'hijack' WHERE tenant_id IS NULL"
            )
            assert cursor.rowcount == 0  # platform rows are read-only from a tenant
            cursor.execute("DELETE FROM isolation_probe_dual WHERE tenant_id IS NULL")
            assert cursor.rowcount == 0
    with tenant_atomic(b):
        assert _names("isolation_probe_dual") == {"platform"}
    assert _names("isolation_probe_dual") == {"platform"}  # platform never sees tenant rows
    assert _denied(lambda: _insert("isolation_probe_dual", a, "platform-forging-a"))


def test_private_dual_scope_hides_platform_and_tenant_rows_from_each_other():
    a = new_id()
    _insert("isolation_probe_dual_private", None, "platform")
    with tenant_atomic(a):
        _insert("isolation_probe_dual_private", a, "a-row")
        assert _names("isolation_probe_dual_private") == {"a-row"}
        assert _denied(lambda: _insert("isolation_probe_dual_private", None, "forged"))
    assert _names("isolation_probe_dual_private") == {"platform"}


# --------------------------------------------------------------------------- operations
def test_enable_tenant_rls_emits_enable_force_and_four_policies():
    editor = _RecordingEditor()
    EnableTenantRLS("t").database_forwards("app", editor, None, None)  # type: ignore[arg-type]
    assert editor.sql[:2] == [
        'ALTER TABLE "t" ENABLE ROW LEVEL SECURITY',
        'ALTER TABLE "t" FORCE ROW LEVEL SECURITY',
    ]
    assert [s.split(" FOR ")[1].split()[0] for s in editor.sql[2:]] == [
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
    ]
    assert all(s.startswith("CREATE POLICY tenant_isolation_") for s in editor.sql[2:])


def test_policy_expressions_per_class():
    standard = tenant_policy_expressions("standard")
    assert standard["select"] == ("(tenant_id = (SELECT public.app_tenant_id()))", None)
    assert standard["update"][0] == standard["update"][1]
    assert str(tenant_policy_expressions("dual")["select"][0]).startswith("(tenant_id IS NULL OR")
    assert "IS NOT DISTINCT FROM" in str(tenant_policy_expressions("dual")["insert"][1])
    assert (
        tenant_policy_expressions("dual_private")["select"][0]
        == tenant_policy_expressions("dual_private")["delete"][0]
    )
    with pytest.raises(ValueError, match="Unknown policy kind"):
        tenant_policy_expressions("bogus")


def test_operations_deconstruct_and_describe():
    assert EnableTenantRLS("t").deconstruct() == ("EnableTenantRLS", [], {"table": "t"})
    assert EnableDualScopeRLS("t", private=True).deconstruct() == (
        "EnableDualScopeRLS",
        [],
        {"table": "t", "private": True},
    )
    assert "private dual-scope" in EnableDualScopeRLS("t", private=True).describe()
    assert InstallTenantContextFunction().deconstruct() == ("InstallTenantContextFunction", [], {})


@pytest.mark.parametrize(
    "operation",
    [EnableTenantRLS("t"), EnableDualScopeRLS("t"), InstallTenantContextFunction()],
)
def test_reversal_is_refused_by_default_and_in_production_staging(settings, operation):
    editor = _RecordingEditor()
    for allowed, env in ((False, "local"), (True, "production"), (True, "staging"), (True, "prod")):
        settings.ERP_ALLOW_ISOLATION_ROLLBACK = allowed
        settings.APP_ENVIRONMENT = env
        with pytest.raises(RuntimeError, match="Refusing to reverse"):
            operation.database_backwards("app", editor, None, None)
    assert editor.sql == []  # nothing executed before the refusal


def test_reversal_allowed_only_on_disposable_databases(settings):
    settings.ERP_ALLOW_ISOLATION_ROLLBACK = True
    settings.APP_ENVIRONMENT = "local"
    refuse_isolation_rollback("x")  # does not raise
    editor = _RecordingEditor()
    EnableTenantRLS("t").database_backwards("app", editor, None, None)  # type: ignore[arg-type]
    assert editor.sql[-2:] == [
        'ALTER TABLE "t" NO FORCE ROW LEVEL SECURITY',
        'ALTER TABLE "t" DISABLE ROW LEVEL SECURITY',
    ]
    editor = _RecordingEditor()
    InstallTenantContextFunction().database_backwards("core", editor, None, None)  # type: ignore[arg-type]
    assert editor.sql == ["DROP FUNCTION public.app_tenant_id()"]  # no CASCADE


def test_function_cannot_be_dropped_while_policies_use_it(owner_dsn):
    import psycopg

    with (
        psycopg.connect(**owner_dsn) as conn,
        pytest.raises(psycopg.errors.DependentObjectsStillExist),
    ):
        conn.execute("DROP FUNCTION public.app_tenant_id()")
