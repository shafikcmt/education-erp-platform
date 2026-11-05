"""ADR-009 foundation: the runtime database role is least-privilege and subject to RLS.

These tests run against PostgreSQL 17 as ``erp_app`` (see conftest.py). Tenant models and the
``tenant_atomic`` helper arrive in Phase 3; here we prove the database layer they rely on.
"""

import uuid

import psycopg
import pytest
from django.conf import settings
from django.db import DatabaseError, connection, transaction

pytestmark = pytest.mark.django_db

RLS_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def _scalar(sql, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()[0]


def test_tests_and_app_run_as_erp_app():
    assert _scalar("SELECT current_user") == settings.TEST_APP_DB_USER == "erp_app"


def test_runtime_role_is_not_privileged():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolreplication "
            "FROM pg_roles WHERE rolname = current_user"
        )
        assert cursor.fetchone() == (False, False, False, False, False)


def test_runtime_role_cannot_create_objects():
    with pytest.raises(DatabaseError, match="permission denied"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("CREATE TABLE should_not_exist (id int)")


def test_runtime_role_cannot_create_temporary_tables():
    with pytest.raises(DatabaseError, match="permission denied"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("CREATE TEMPORARY TABLE should_not_exist (id int)")


def test_public_cannot_connect_or_create_temp_on_the_database():
    assert not _scalar("SELECT has_database_privilege('public', current_database(), 'CONNECT')")
    assert not _scalar("SELECT has_database_privilege('public', current_database(), 'TEMPORARY')")


@pytest.mark.parametrize(
    "ddl",
    [
        "ALTER TABLE identity_user ADD COLUMN x int",
        "DROP TABLE identity_user",
        "ALTER TABLE identity_user DISABLE ROW LEVEL SECURITY",
        "CREATE INDEX should_not_exist ON identity_user (email)",
    ],
)
def test_runtime_role_cannot_change_application_schema(ddl):
    """Only erp_owner (migrations) may change the schema; erp_app is DML-only."""
    with (
        pytest.raises(DatabaseError, match=r"must be owner|permission denied"),
        transaction.atomic(),
    ):
        with connection.cursor() as cursor:
            cursor.execute(ddl)


def test_runtime_role_cannot_assume_owner_role():
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET ROLE erp_owner")


def test_runtime_role_does_not_own_application_tables():
    owners = _scalar(
        "SELECT array_agg(DISTINCT tableowner) FROM pg_tables WHERE schemaname = 'public'"
    )
    assert owners == ["erp_owner"]


def test_runtime_role_has_dml_on_application_tables():
    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        assert _scalar("SELECT has_table_privilege('identity_user', %s)", [privilege])
    assert not _scalar("SELECT has_table_privilege('identity_user', 'TRUNCATE')")


def test_required_extensions_installed():
    installed = set(_scalar("SELECT array_agg(extname) FROM pg_extension"))
    assert {"vector", "pg_trgm", "btree_gist", "citext"} <= installed


def test_platform_role_exists_with_bypassrls_but_cannot_log_in():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rolcanlogin, rolbypassrls FROM pg_roles WHERE rolname = 'erp_platform'"
        )
        assert cursor.fetchone() == (False, True)


@pytest.fixture
def rls_probe_table(owner_dsn):
    """Throwaway FORCE-RLS table using the exact ADR-009 policy, created by the owner."""
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    with psycopg.connect(**owner_dsn, autocommit=True) as owner:
        owner.execute(
            "CREATE TABLE _rls_probe (id serial PRIMARY KEY, tenant_id uuid NOT NULL, v text)"
        )
        owner.execute("ALTER TABLE _rls_probe ENABLE ROW LEVEL SECURITY")
        owner.execute("ALTER TABLE _rls_probe FORCE ROW LEVEL SECURITY")
        owner.execute(
            f"CREATE POLICY tenant_isolation ON _rls_probe "
            f"USING ({RLS_PREDICATE}) WITH CHECK ({RLS_PREDICATE})"
        )
        for tenant, value in ((tenant_a, "a1"), (tenant_a, "a2"), (tenant_b, "b1")):
            with owner.transaction():
                owner.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant)])
                owner.execute(
                    "INSERT INTO _rls_probe (tenant_id, v) VALUES (%s, %s)", [tenant, value]
                )
    app_dsn = {
        **owner_dsn,
        "user": settings.TEST_APP_DB_USER,
        "password": settings.TEST_APP_DB_PASSWORD,
    }
    try:
        yield app_dsn, tenant_a, tenant_b
    finally:
        with psycopg.connect(**owner_dsn, autocommit=True) as owner:
            owner.execute("DROP TABLE IF EXISTS _rls_probe")


def test_rls_fails_closed_without_tenant_context(rls_probe_table):
    app_dsn, _, _ = rls_probe_table
    with psycopg.connect(**app_dsn) as app:
        assert app.execute("SELECT count(*) FROM _rls_probe").fetchone()[0] == 0


def test_rls_scopes_reads_to_transaction_tenant(rls_probe_table):
    app_dsn, tenant_a, tenant_b = rls_probe_table
    with psycopg.connect(**app_dsn) as app:
        with app.transaction():
            app.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant_a)])
            rows = app.execute("SELECT v FROM _rls_probe ORDER BY v").fetchall()
            assert rows == [("a1",), ("a2",)]
        with app.transaction():
            app.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant_b)])
            assert app.execute("SELECT v FROM _rls_probe").fetchall() == [("b1",)]


def test_transaction_scoped_tenant_context_does_not_leak(rls_probe_table):
    app_dsn, tenant_a, _ = rls_probe_table
    with psycopg.connect(**app_dsn) as app:
        with app.transaction():
            app.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant_a)])
            assert app.execute("SELECT count(*) FROM _rls_probe").fetchone()[0] == 2
        # Same pooled connection, next transaction: context is gone -> fail closed.
        assert app.execute("SELECT count(*) FROM _rls_probe").fetchone()[0] == 0
        assert app.execute("SELECT current_setting('app.tenant_id', true)").fetchone()[0] in (
            "",
            None,
        )


def test_rls_with_check_blocks_cross_tenant_writes(rls_probe_table):
    app_dsn, tenant_a, tenant_b = rls_probe_table
    with psycopg.connect(**app_dsn) as app:
        with pytest.raises(psycopg.errors.InsufficientPrivilege), app.transaction():
            app.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant_a)])
            app.execute("INSERT INTO _rls_probe (tenant_id, v) VALUES (%s, 'x')", [tenant_b])


def test_rls_hides_other_tenant_rows_from_update_and_delete(rls_probe_table):
    app_dsn, tenant_a, _ = rls_probe_table
    with psycopg.connect(**app_dsn) as app, app.transaction():
        app.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant_a)])
        assert app.execute("UPDATE _rls_probe SET v = 'changed' WHERE v = 'b1'").rowcount == 0
        assert app.execute("DELETE FROM _rls_probe WHERE v = 'b1'").rowcount == 0
