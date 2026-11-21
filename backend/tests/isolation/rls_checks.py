"""Deterministic catalogue checks for tenant isolation (plan §5.3; ADR-046).

Each ``check_*`` function inspects the PostgreSQL catalogue of one schema and returns a sorted
list of human-readable violations (empty = compliant). ``test_rls_coverage.py`` runs them on
the migrated test database and fails on any violation; meta-tests run them on a throwaway
schema with deliberately broken tables to prove each check detects what it claims to.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from tests.isolation import registry

BACKEND_DIR = Path(__file__).resolve().parents[2]

PolicySig = frozenset[tuple[str, str, bool, tuple[int, ...], str | None, str | None]]


@dataclass(frozen=True)
class TableInfo:
    name: str
    rls: bool
    forced: bool
    columns: Mapping[str, bool]  # column -> NOT NULL

    @property
    def has_tenant_id(self) -> bool:
        return "tenant_id" in self.columns


def _rows(cursor: Any, sql: str, params: Iterable[Any] = ()) -> list[tuple[Any, ...]]:
    cursor.execute(sql, list(params))
    return list(cursor.fetchall())


def load_tables(cursor: Any, schema: str) -> dict[str, TableInfo]:
    tables = _rows(
        cursor,
        """
        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %s AND c.relkind IN ('r', 'p')
        """,
        [schema],
    )
    cols = _rows(
        cursor,
        """
        SELECT c.relname, a.attname, a.attnotnull
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %s AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped
        """,
        [schema],
    )
    columns: dict[str, dict[str, bool]] = {}
    for table, col, notnull in cols:
        columns.setdefault(table, {})[col] = bool(notnull)
    return {
        name: TableInfo(name, bool(rls), bool(forced), columns.get(name, {}))
        for name, rls, forced in tables
    }


def load_policies(cursor: Any, schema: str) -> dict[str, PolicySig]:
    rows = _rows(
        cursor,
        """
        SELECT c.relname, p.polname, p.polcmd::text, p.polpermissive, p.polroles::oid[],
               pg_catalog.pg_get_expr(p.polqual, p.polrelid),
               pg_catalog.pg_get_expr(p.polwithcheck, p.polrelid)
        FROM pg_policy p
        JOIN pg_class c ON c.oid = p.polrelid JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %s
        """,
        [schema],
    )
    out: dict[str, set[tuple[str, str, bool, tuple[int, ...], str | None, str | None]]] = {}
    for table, name, cmd, permissive, roles, qual, check in rows:
        out.setdefault(table, set()).add(
            (name, cmd, bool(permissive), tuple(sorted(int(r) for r in roles)), qual, check)
        )
    return {table: frozenset(sig) for table, sig in out.items()}


# --------------------------------------------------------------------------- table classes
def check_table_classes(
    tables: Mapping[str, TableInfo],
    policies: Mapping[str, PolicySig],
    reference: Mapping[str, PolicySig],
    *,
    dual: Mapping[str, str] | None = None,
    self_scoped: Mapping[str, str] | None = None,
    pending: Mapping[str, registry.Pending] | None = None,
    allowlist: Mapping[str, registry.AllowEntry] | None = None,
    owner_policies: frozenset[tuple[str, str]] | None = None,
) -> list[str]:
    dual = registry.DUAL_SCOPE_TABLES if dual is None else dual
    self_scoped = registry.SELF_SCOPED_TABLES if self_scoped is None else self_scoped
    pending = registry.PENDING_RLS if pending is None else pending
    allowlist = registry.REGISTRY_ALLOWLIST if allowlist is None else allowlist
    owner_policies = registry.OWNER_POLICIES if owner_policies is None else owner_policies
    problems: list[str] = []

    for name, table in sorted(tables.items()):
        sig = policies.get(name, frozenset())
        public_sig = frozenset(p for p in sig if p[3] == (0,))
        if name in pending:
            if table.rls or table.forced or sig:
                problems.append(
                    f"{name}: scheduled for RLS in {pending[name].milestone} but partially "
                    "configured; finish it and move it to the registry"
                )
            continue
        if name in dual:
            kind = dual[name]
            if not table.has_tenant_id:
                problems.append(f"{name}: dual-scope table without tenant_id")
            problems += _check_rls(name, table, public_sig, reference.get(kind), kind)
        elif name in self_scoped:
            if not (table.rls and table.forced):
                problems.append(f"{name}: self-scoped table without ENABLE + FORCE RLS")
            if {p[1] for p in public_sig} != {"r", "a", "w", "d"}:
                problems.append(f"{name}: self-scoped table needs one policy per command")
        elif table.has_tenant_id:
            if not table.columns["tenant_id"]:
                problems.append(
                    f"{name}: nullable tenant_id on an unregistered table (register it as "
                    "dual-scope or make tenant_id NOT NULL)"
                )
            problems += _check_rls(name, table, public_sig, reference.get("standard"), "standard")
        else:
            if table.rls or table.forced or sig:
                problems.append(f"{name}: row security on an unregistered table")
            if name not in allowlist:
                problems.append(f"{name}: table without RLS is not on the registry allow-list")

        for policy in sig - public_sig:
            if (name, policy[0]) not in owner_policies:
                problems.append(f"{name}: role-specific policy {policy[0]!r} is not approved")
            elif policy[1] != "r":
                problems.append(f"{name}: owner-only policy {policy[0]!r} must be SELECT only")
    for name in sorted(set(allowlist) - set(tables)):
        problems.append(f"{name}: allow-list entry for a table that does not exist")
    return problems


def _check_rls(
    name: str, table: TableInfo, sig: PolicySig, expected: PolicySig | None, kind: str
) -> list[str]:
    problems: list[str] = []
    if not table.rls:
        problems.append(f"{name}: RLS not enabled ({kind})")
    if not table.forced:
        problems.append(f"{name}: RLS not forced ({kind})")
    if expected is None:
        problems.append(f"{name}: no reference policy shape for {kind!r}")
    elif sig != expected:
        problems.append(f"{name}: policies differ from the {kind} reference shape")
    return problems


# --------------------------------------------------------------------------- allow-list
@cache
def _functions_in(path: Path) -> frozenset[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return frozenset(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    )


def check_allowlist(allowlist: Mapping[str, registry.AllowEntry] | None = None) -> list[str]:
    allowlist = registry.REGISTRY_ALLOWLIST if allowlist is None else allowlist
    problems: list[str] = []
    for table, entry in sorted(allowlist.items()):
        if len(entry.justification.strip()) < 20:
            problems.append(f"{table}: allow-list justification missing or too short")
        if not entry.tests:
            problems.append(f"{table}: allow-list entry names no access-control tests")
        for test_id in entry.tests:
            path_part, _, func = test_id.partition("::")
            path = BACKEND_DIR / path_part
            if not func or not path.is_file() or func not in _functions_in(path):
                problems.append(f"{table}: access-control test {test_id!r} does not exist")
    return problems


# --------------------------------------------------------------------------- constraints
def check_foreign_keys(cursor: Any, schema: str, standard: set[str]) -> list[str]:
    rows = _rows(
        cursor,
        """
        SELECT con.conname, src.relname, dst.relname,
          ARRAY(SELECT a.attname FROM unnest(con.conkey) WITH ORDINALITY k(n, o)
                JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.n ORDER BY k.o),
          ARRAY(SELECT a.attname FROM unnest(con.confkey) WITH ORDINALITY k(n, o)
                JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k.n ORDER BY k.o)
        FROM pg_constraint con
        JOIN pg_class src ON src.oid = con.conrelid JOIN pg_class dst ON dst.oid = con.confrelid
        JOIN pg_namespace n ON n.oid = con.connamespace
        WHERE con.contype = 'f' AND n.nspname = %s
        """,
        [schema],
    )
    problems = []
    for conname, src, dst, cols, fcols in rows:
        if src in standard and dst in standard:
            pairs = list(zip(cols, fcols, strict=True))
            if ("tenant_id", "tenant_id") not in pairs:
                problems.append(
                    f"{src}.{conname}: tenant-to-tenant foreign key without tenant_id on both "
                    "sides (FK checks bypass RLS)"
                )
    return sorted(problems)


def check_unique_constraints(
    cursor: Any,
    schema: str,
    standard: set[str],
    exceptions: frozenset[tuple[str, tuple[str, ...]]] | None = None,
) -> list[str]:
    exceptions = registry.UNIQUE_EXCEPTIONS if exceptions is None else exceptions
    rows = _rows(
        cursor,
        """
        SELECT c.relname, i.relname, ix.indisprimary,
          ARRAY(SELECT COALESCE(a.attname, '<expr>')
                FROM unnest(ix.indkey::int2[]) WITH ORDINALITY k(n, o)
                LEFT JOIN pg_attribute a ON a.attrelid = ix.indrelid AND a.attnum = k.n
                ORDER BY k.o)
        FROM pg_index ix
        JOIN pg_class c ON c.oid = ix.indrelid JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %s AND ix.indisunique
        """,
        [schema],
    )
    problems = []
    for table, index, primary, cols in rows:
        if table not in standard or primary:
            continue
        if cols[0] != "tenant_id" and (table, tuple(cols)) not in exceptions:
            problems.append(f"{table}.{index}: unique constraint does not start with tenant_id")
    return sorted(problems)


# --------------------------------------------------------------------------- functions
def check_definer_functions(
    cursor: Any, schema: str, approved: frozenset[str] | None = None, owner: str = "erp_owner"
) -> list[str]:
    approved = registry.DEFINER_FUNCTIONS if approved is None else approved
    rows = _rows(
        cursor,
        """
        SELECT p.proname, pg_catalog.pg_get_userbyid(p.proowner), p.provolatile::text,
               COALESCE(p.proconfig, '{}'::text[]), p.proacl IS NULL,
               EXISTS (SELECT 1 FROM aclexplode(p.proacl) acl
                       WHERE acl.grantee = 0 AND acl.privilege_type = 'EXECUTE')
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = %s AND p.prosecdef
        """,
        [schema],
    )
    problems = []
    for name, fowner, volatility, config, default_acl, public_exec in rows:
        if name not in approved:
            problems.append(f"{name}(): SECURITY DEFINER function is not on the approved list")
        if not any(str(c).startswith("search_path=") for c in config):
            problems.append(f"{name}(): SECURITY DEFINER without a pinned search_path")
        if default_acl or public_exec:
            problems.append(f"{name}(): SECURITY DEFINER executable by PUBLIC")
        if fowner != owner:
            problems.append(f"{name}(): SECURITY DEFINER not owned by {owner}")
        if volatility != "s":
            problems.append(f"{name}(): SECURITY DEFINER must be STABLE")
    return sorted(problems)


# --------------------------------------------------------------------------- models
def check_models(dual: Iterable[str] = (), pending: Iterable[str] = ()) -> list[str]:
    from django.apps import apps

    from apps.core.tenancy.models import TenantManager, TenantScopedModel

    # Self-scoped registry rows (Phase 4: subscriptions, items, overrides) are read by the
    # platform without a context by design; their RLS is checked by check_table_classes.
    exempt = (
        set(dual)
        | set(pending)
        | set(registry.DUAL_SCOPE_TABLES)
        | set(registry.PENDING_RLS)
        | set(registry.SELF_SCOPED_TABLES)
    )
    problems = []
    for model in apps.get_models():
        meta = model._meta
        if meta.abstract or meta.proxy or not meta.managed:
            continue
        names = {f.name for f in meta.concrete_fields} | {f.attname for f in meta.concrete_fields}
        if not names & {"tenant", "tenant_id"} or meta.db_table in exempt:
            continue
        if not issubclass(model, TenantScopedModel):
            problems.append(f"{meta.label}: has tenant_id but does not inherit TenantScopedModel")
        elif not isinstance(model._base_manager, TenantManager):
            problems.append(f"{meta.label}: base manager is not the fail-closed TenantManager")
    return sorted(problems)


def standard_tables(tables: Mapping[str, TableInfo]) -> set[str]:
    special = (
        set(registry.DUAL_SCOPE_TABLES)
        | set(registry.PENDING_RLS)
        | set(registry.SELF_SCOPED_TABLES)
    )
    return {name for name, t in tables.items() if t.has_tenant_id and name not in special}
