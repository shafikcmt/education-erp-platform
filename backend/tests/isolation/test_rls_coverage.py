"""CI-blocking RLS coverage check (plan §5.3; ADR-046).

Runs the catalogue checks on the migrated test database, then proves with meta-tests on a
throwaway schema that each check fails on a real violation.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from django.db import connection

from tests.isolation import registry, rls_checks

pytestmark = pytest.mark.django_db


@pytest.fixture
def catalogue() -> tuple[dict[str, rls_checks.TableInfo], dict[str, rls_checks.PolicySig]]:
    with connection.cursor() as cursor:
        return rls_checks.load_tables(cursor, "public"), rls_checks.load_policies(cursor, "public")


def _reference(policies: dict[str, rls_checks.PolicySig]) -> dict[str, rls_checks.PolicySig]:
    return {kind: policies[table] for kind, table in registry.REFERENCE_PROBES.items()}


# --------------------------------------------------------------------------- the real gate
def test_every_table_is_classified_and_correctly_protected(catalogue):
    tables, policies = catalogue
    assert rls_checks.check_table_classes(tables, policies, _reference(policies)) == []


def test_reference_probes_have_four_per_command_policies(catalogue):
    tables, policies = catalogue
    for kind, table in registry.REFERENCE_PROBES.items():
        assert tables[table].rls and tables[table].forced, kind
        sig = policies[table]
        assert {p[1] for p in sig} == {"r", "a", "w", "d"}, kind
        assert {p[0] for p in sig} == {f"tenant_isolation_{c}" for c in rls_checks_cmds()}
        assert all(p[2] and p[3] == (0,) for p in sig), "permissive, PUBLIC"
        assert all("app_tenant_id()" in (p[4] or "") + (p[5] or "") for p in sig)


def rls_checks_cmds() -> tuple[str, ...]:
    from apps.core.db_operations import POLICY_COMMANDS

    return POLICY_COMMANDS


def test_allowlist_entries_are_justified_and_name_existing_tests():
    assert rls_checks.check_allowlist() == []


def test_tenant_foreign_keys_include_tenant_id(catalogue):
    tables, _ = catalogue
    with connection.cursor() as cursor:
        assert (
            rls_checks.check_foreign_keys(cursor, "public", rls_checks.standard_tables(tables))
            == []
        )


def test_unique_constraints_start_with_tenant_id(catalogue):
    tables, _ = catalogue
    with connection.cursor() as cursor:
        standard = rls_checks.standard_tables(tables)
        assert rls_checks.check_unique_constraints(cursor, "public", standard) == []


def test_no_unapproved_security_definer_functions():
    with connection.cursor() as cursor:
        assert rls_checks.check_definer_functions(cursor, "public") == []


def test_tenant_models_use_tenant_scoped_model():
    assert rls_checks.check_models() == []


def test_pending_tables_are_documented_for_a_later_milestone():
    for table, pending in registry.PENDING_RLS.items():
        assert pending.milestone.startswith("M") and pending.note, table
        assert pending.kind in registry.REFERENCE_PROBES, table


def test_app_tenant_id_is_invoker_and_not_public():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.prosecdef, p.provolatile::text, p.proacl IS NULL,
                   EXISTS (SELECT 1 FROM aclexplode(p.proacl) a
                           WHERE a.grantee = 0 AND a.privilege_type = 'EXECUTE'),
                   pg_catalog.pg_get_userbyid(p.proowner),
                   has_function_privilege('erp_app', p.oid, 'EXECUTE')
            FROM pg_proc p WHERE p.proname = 'app_tenant_id'
              AND p.pronamespace = 'public'::regnamespace
            """
        )
        definer, volatility, default_acl, public_exec, owner, app_exec = cursor.fetchone()
    assert (definer, volatility, default_acl, public_exec) == (False, "s", False, False)
    assert owner == "erp_owner" and app_exec is True


# --------------------------------------------------------------------------- meta-tests
@pytest.fixture
def scratch(owner_dsn: dict[str, Any]) -> Iterator[tuple[psycopg.Connection, str]]:
    """A throwaway schema (owner connection, autocommit) dropped afterwards."""
    schema = f"rls_meta_{uuid.uuid4().hex[:10]}"
    conn = psycopg.connect(**owner_dsn, autocommit=True)
    conn.execute(f"CREATE SCHEMA {schema}")
    try:
        yield conn, schema
    finally:
        conn.execute(f"DROP SCHEMA {schema} CASCADE")
        conn.close()


def _scratch_catalogue(conn: psycopg.Connection, schema: str):
    with conn.cursor() as cur:
        return rls_checks.load_tables(cur, schema), rls_checks.load_policies(cur, schema)


def _reference_from_public() -> dict[str, rls_checks.PolicySig]:
    with connection.cursor() as cursor:
        return _reference(rls_checks.load_policies(cursor, "public"))


def _policies_sql(table: str, kind: str) -> str:
    from apps.core.db_operations import policy_name, tenant_policy_expressions

    parts = [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
    ]
    for cmd, (using, check) in tenant_policy_expressions(kind).items():
        sql = f"CREATE POLICY {policy_name(cmd)} ON {table} FOR {cmd.upper()}"
        sql += f" USING {using}" if using else ""
        sql += f" WITH CHECK {check}" if check else ""
        parts.append(sql)
    return "; ".join(parts)


def _classes(conn, schema, **kw):
    tables, policies = _scratch_catalogue(conn, schema)
    defaults: dict[str, Any] = {
        "dual": {},
        "self_scoped": {},
        "pending": {},
        "allowlist": {},
        "owner_policies": frozenset(),
    }
    defaults.update(kw)
    return rls_checks.check_table_classes(tables, policies, _reference_from_public(), **defaults)


def test_meta_compliant_standard_table_passes(scratch):
    conn, s = scratch
    conn.execute(f"CREATE TABLE {s}.good (id uuid PRIMARY KEY, tenant_id uuid NOT NULL)")
    conn.execute(_policies_sql(f"{s}.good", "standard"))
    assert _classes(conn, s) == []


def test_meta_detects_missing_enable_force_and_policies(scratch):
    conn, s = scratch
    conn.execute(f"CREATE TABLE {s}.no_rls (id uuid PRIMARY KEY, tenant_id uuid NOT NULL)")
    conn.execute(f"CREATE TABLE {s}.not_forced (id uuid PRIMARY KEY, tenant_id uuid NOT NULL)")
    conn.execute(_policies_sql(f"{s}.not_forced", "standard"))
    conn.execute(f"ALTER TABLE {s}.not_forced NO FORCE ROW LEVEL SECURITY")
    problems = _classes(conn, s)
    assert "no_rls: RLS not enabled (standard)" in problems
    assert "no_rls: RLS not forced (standard)" in problems
    assert "no_rls: policies differ from the standard reference shape" in problems
    assert "not_forced: RLS not forced (standard)" in problems


def test_meta_detects_wrongly_shaped_or_missing_command_policies(scratch):
    conn, s = scratch
    conn.execute(f"CREATE TABLE {s}.leaky (id uuid PRIMARY KEY, tenant_id uuid NOT NULL)")
    conn.execute(_policies_sql(f"{s}.leaky", "standard"))
    conn.execute(f"DROP POLICY tenant_isolation_select ON {s}.leaky")
    conn.execute(f"CREATE POLICY tenant_isolation_select ON {s}.leaky FOR SELECT USING (true)")
    conn.execute(f"CREATE TABLE {s}.no_delete (id uuid PRIMARY KEY, tenant_id uuid NOT NULL)")
    conn.execute(_policies_sql(f"{s}.no_delete", "standard"))
    conn.execute(f"DROP POLICY tenant_isolation_delete ON {s}.no_delete")
    problems = _classes(conn, s)
    assert "leaky: policies differ from the standard reference shape" in problems
    assert "no_delete: policies differ from the standard reference shape" in problems


def test_meta_detects_unregistered_dual_scope_and_self_scoped_tables(scratch):
    conn, s = scratch
    conn.execute(f"CREATE TABLE {s}.maybe_dual (id uuid PRIMARY KEY, tenant_id uuid)")
    conn.execute(_policies_sql(f"{s}.maybe_dual", "dual"))
    conn.execute(f"CREATE TABLE {s}.selfish (id uuid PRIMARY KEY)")
    conn.execute(f"ALTER TABLE {s}.selfish ENABLE ROW LEVEL SECURITY")
    problems = _classes(conn, s)
    assert any(
        p.startswith("maybe_dual: nullable tenant_id on an unregistered table") for p in problems
    )
    assert "selfish: row security on an unregistered table" in problems
    # Registered correctly, both pass the class check.
    conn.execute(f"ALTER TABLE {s}.selfish FORCE ROW LEVEL SECURITY")
    for cmd in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        clause = "WITH CHECK (true)" if cmd == "INSERT" else "USING (true)"
        conn.execute(f"CREATE POLICY p_{cmd.lower()} ON {s}.selfish FOR {cmd} {clause}")
    assert _classes(conn, s, dual={"maybe_dual": "dual"}, self_scoped={"selfish": "id"}) == []


def test_meta_detects_tables_missing_from_the_allowlist_and_bad_entries(scratch):
    conn, s = scratch
    conn.execute(f"CREATE TABLE {s}.registry_thing (id uuid PRIMARY KEY)")
    assert _classes(conn, s) == [
        "registry_thing: table without RLS is not on the registry allow-list"
    ]
    bad = {
        "registry_thing": registry.AllowEntry("too short", ()),
        "ghost": registry.AllowEntry(
            "A long enough justification text.", ("tests/nope.py::test_x",)
        ),
        "typo": registry.AllowEntry(
            "A long enough justification text.",
            ("apps/core/tests/test_db_grants.py::test_does_not_exist",),
        ),
    }
    problems = rls_checks.check_allowlist(bad)
    assert "registry_thing: allow-list justification missing or too short" in problems
    assert "registry_thing: allow-list entry names no access-control tests" in problems
    assert "ghost: access-control test 'tests/nope.py::test_x' does not exist" in problems
    assert any(p.startswith("typo: access-control test") for p in problems)
    assert "ghost: allow-list entry for a table that does not exist" in _classes(
        conn, s, allowlist={"registry_thing": bad["registry_thing"], "ghost": bad["ghost"]}
    )


def test_meta_detects_half_configured_pending_tables(scratch):
    conn, s = scratch
    conn.execute(f"CREATE TABLE {s}.later (id uuid PRIMARY KEY, tenant_id uuid)")
    pending = {"later": registry.Pending("dual", "M6", "note")}
    assert _classes(conn, s, pending=pending) == []
    conn.execute(f"ALTER TABLE {s}.later ENABLE ROW LEVEL SECURITY")
    assert _classes(conn, s, pending=pending) == [
        "later: scheduled for RLS in M6 but partially configured; "
        "finish it and move it to the registry"
    ]


def test_meta_detects_unapproved_role_specific_policies(scratch):
    conn, s = scratch
    conn.execute(f"CREATE TABLE {s}.good (id uuid PRIMARY KEY, tenant_id uuid NOT NULL)")
    conn.execute(_policies_sql(f"{s}.good", "standard"))
    conn.execute(f"CREATE POLICY definer_peek ON {s}.good FOR UPDATE TO erp_owner USING (true)")
    assert "good: role-specific policy 'definer_peek' is not approved" in _classes(conn, s)
    problems = _classes(conn, s, owner_policies=frozenset({("good", "definer_peek")}))
    assert problems == ["good: owner-only policy 'definer_peek' must be SELECT only"]


def test_meta_detects_tenant_foreign_keys_without_tenant_id(scratch):
    conn, s = scratch
    conn.execute(
        f"CREATE TABLE {s}.parent (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, "
        "UNIQUE (tenant_id, id))"
    )
    conn.execute(
        f"CREATE TABLE {s}.child_bad (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, "
        f"parent_id uuid REFERENCES {s}.parent (id))"
    )
    conn.execute(
        f"CREATE TABLE {s}.child_ok (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, parent_id uuid, "
        f"FOREIGN KEY (tenant_id, parent_id) REFERENCES {s}.parent (tenant_id, id))"
    )
    with conn.cursor() as cur:
        problems = rls_checks.check_foreign_keys(cur, s, {"parent", "child_bad", "child_ok"})
    assert len(problems) == 1 and problems[0].startswith("child_bad.")


def test_meta_detects_unique_constraints_not_starting_with_tenant_id(scratch):
    conn, s = scratch
    conn.execute(
        f"CREATE TABLE {s}.t (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, code text, "
        "email text, CONSTRAINT t_code UNIQUE (tenant_id, code), "
        "CONSTRAINT t_email UNIQUE (email))"
    )
    conn.execute(f"CREATE UNIQUE INDEX t_lower ON {s}.t (lower(email))")
    with conn.cursor() as cur:
        problems = rls_checks.check_unique_constraints(cur, s, {"t"})
        assert problems == [
            "t.t_email: unique constraint does not start with tenant_id",
            "t.t_lower: unique constraint does not start with tenant_id",
        ]
        allowed = frozenset({("t", ("email",)), ("t", ("<expr>",))})
        assert rls_checks.check_unique_constraints(cur, s, {"t"}, allowed) == []


def test_meta_detects_unsafe_security_definer_functions(scratch):
    conn, s = scratch
    conn.execute(
        f"CREATE FUNCTION {s}.bad() RETURNS int LANGUAGE sql SECURITY DEFINER AS 'SELECT 1'"
    )
    conn.execute(
        f"CREATE FUNCTION {s}.good() RETURNS int LANGUAGE sql STABLE SECURITY DEFINER "
        "SET search_path = pg_catalog, pg_temp AS 'SELECT 1'"
    )
    conn.execute(f"REVOKE ALL ON FUNCTION {s}.good() FROM PUBLIC")
    with conn.cursor() as cur:
        problems = rls_checks.check_definer_functions(cur, s, frozenset({"good"}))
    assert problems == [
        "bad(): SECURITY DEFINER executable by PUBLIC",
        "bad(): SECURITY DEFINER function is not on the approved list",
        "bad(): SECURITY DEFINER must be STABLE",
        "bad(): SECURITY DEFINER without a pinned search_path",
    ]


def test_meta_detects_tenant_models_without_tenant_scoped_model():
    from django.db import models

    class Rogue(models.Model):
        tenant_id = models.UUIDField()

        class Meta:
            app_label = "isolation_probe"
            db_table = "isolation_probe_rogue"

        def __str__(self) -> str:
            return str(self.tenant_id)

    from django.apps import apps

    try:
        assert (
            "isolation_probe.Rogue: has tenant_id but does not inherit TenantScopedModel"
            in rls_checks.check_models()
        )
    finally:
        apps.all_models["isolation_probe"].pop("rogue", None)
        apps.clear_cache()
