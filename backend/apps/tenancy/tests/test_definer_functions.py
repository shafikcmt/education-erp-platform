"""SECURITY DEFINER functions F1-F3 and their wrappers (Phase 3 M2; plan §7 threat model).

Each test maps to a row of the per-function threat model: uniform results (no enumeration),
minimal columns, no PUBLIC execute, pinned search_path, owner-only SELECT policies that never
apply to ``erp_app``, single wrapper callers, and use only inside the catalogued
``platform_scope`` operation.
"""

from __future__ import annotations

import re
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import psycopg
import pytest
from django.db import connection
from django.utils import timezone

from apps.core.tenancy import PlatformScopeError, TenantContextConflict, tenant_atomic
from apps.core.tenancy.platform import platform_scope
from apps.tenancy import models as m
from apps.tenancy.rules import TenantStatus
from apps.tenancy.selectors import platform as wrappers
from tests.helpers import make_user

pytestmark = pytest.mark.django_db

FUNCTIONS = {
    "tenancy_resolve_host": ["tenant_id", "status"],
    "tenancy_memberships_of": ["tenant_id", "slug", "name", "tenant_status", "membership_status"],
    "tenancy_support_sessions_of": [
        "session_id",
        "tenant_id",
        "tenant_slug",
        "status",
        "starts_at",
        "ends_at",
    ],
}


def _one(sql: str, params: list[Any] | None = None) -> Any:
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return cursor.fetchall()


def _tenant_with_domain(factory: Any, status: str, *, verified: bool = True) -> Any:
    ctx = factory(status=status)
    with tenant_atomic(ctx):
        m.TenantDomain.objects.create(
            domain=f"{ctx.slug}.tenants.test",
            is_primary=True,
            verified_at=timezone.now() if verified else None,
        )
    return ctx


def _resolve(host: str | None) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = _one("SELECT * FROM public.tenancy_resolve_host(%s)", [host])
    return rows


# --------------------------------------------------------------------------- catalogue
def test_functions_are_definer_stable_pinned_owned_and_not_public():
    for name, columns in FUNCTIONS.items():
        rows = _one(
            """
            SELECT p.prosecdef, p.provolatile::text, p.proconfig,
                   pg_catalog.pg_get_userbyid(p.proowner), p.proacl IS NULL,
                   has_function_privilege('erp_app', p.oid, 'EXECUTE'),
                   EXISTS (SELECT 1 FROM aclexplode(p.proacl) a
                           WHERE a.grantee = 0 AND a.privilege_type = 'EXECUTE'),
                   pg_catalog.pg_get_functiondef(p.oid)
            FROM pg_proc p WHERE p.proname = %s AND p.pronamespace = 'public'::regnamespace
            """,
            [name],
        )
        assert len(rows) == 1, name
        definer, volatility, config, owner, default_acl, app_exec, public_exec, body = rows[0]
        assert (definer, volatility, owner, default_acl, public_exec) == (
            True,
            "s",
            "erp_owner",
            False,
            False,
        )
        assert app_exec is True
        assert config == ["search_path=pg_catalog, public, pg_temp"], name
        assert "set_config" not in body and "EXECUTE " not in body.upper().replace(
            "EXECUTE FUNCTION", ""
        )
        # Every relation reference is schema-qualified.
        for table in re.findall(r"(?:FROM|JOIN)\s+([a-z_.]+)", body):
            assert table.startswith("public."), (name, table)
        result_cols = _one("SELECT unnest(proargnames) FROM pg_proc WHERE proname = %s", [name])
        assert [c[0] for c in result_cols][1:] == columns, name


def test_owner_only_policies_are_select_only_and_never_apply_to_the_runtime_role():
    rows = _one(
        """
        SELECT c.relname, p.polname, p.polcmd::text,
               ARRAY(SELECT rolname FROM pg_roles WHERE oid = ANY(p.polroles))
        FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
        WHERE p.polname LIKE 'definer\\_%%'
        """
    )
    assert {(r[0], r[1]) for r in rows} == {
        ("tenancy_tenantdomain", "definer_resolve_host"),
        ("tenancy_membership", "definer_memberships_of"),
        ("tenancy_supportsession", "definer_support_sessions_of"),
    }
    assert all(r[2] == "r" and r[3] == ["erp_owner"] for r in rows)


def test_runtime_role_cannot_read_through_the_owner_policies(tenant_factory):
    _tenant_with_domain(tenant_factory, TenantStatus.ACTIVE)
    # erp_app without a tenant context sees no domain, membership or support row.
    for table in ("tenancy_tenantdomain", "tenancy_membership", "tenancy_supportsession"):
        assert _one(f"SELECT count(*) FROM {table}") == [(0,)]


# --------------------------------------------------------------------------- F1
def test_f1_resolves_only_verified_hosts_of_resolvable_tenants(tenant_factory):
    resolvable = {
        status: _tenant_with_domain(tenant_factory, status)
        for status in (TenantStatus.ACTIVE, TenantStatus.SUSPENDED, TenantStatus.OFFBOARDING)
    }
    for status, ctx in resolvable.items():
        assert _resolve(f"{ctx.slug}.tenants.test") == [(ctx.id, status)]
    hidden = [
        _tenant_with_domain(tenant_factory, TenantStatus.PROVISIONING),
        _tenant_with_domain(tenant_factory, TenantStatus.DELETED),
        _tenant_with_domain(tenant_factory, TenantStatus.ACTIVE, verified=False),
    ]
    results = [_resolve(f"{ctx.slug}.tenants.test") for ctx in hidden]
    results.append(_resolve("unknown.tenants.test"))
    assert results == [[], [], [], []]  # indistinguishable from unknown


@pytest.mark.parametrize(
    "host",
    [
        "",
        "ACME.tenants.test",
        "acme",
        "1.2.3.4",
        "acme.tenants.test.",
        "a" * 254,
        "ac me.test",
        None,
    ],
)
def test_f1_rejects_malformed_hosts(host, tenant_factory):
    _tenant_with_domain(tenant_factory, TenantStatus.ACTIVE)
    assert _resolve(host) == []


def test_f1_ignores_search_path_hijacking(owner_dsn):
    """A temporary table shadowing ``tenancy_tenantdomain`` has no effect (pinned path,
    schema-qualified references). Run as the owner, which may create temporary objects."""
    with psycopg.connect(**owner_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "CREATE TEMP TABLE tenancy_tenantdomain "
            "(tenant_id uuid, domain text, verified_at timestamptz)"
        )
        cur.execute("CREATE TEMP TABLE tenancy_tenant (id uuid, status text)")
        tid = uuid.uuid4()
        cur.execute("INSERT INTO pg_temp.tenancy_tenant VALUES (%s, 'active')", [tid])
        cur.execute(
            "INSERT INTO pg_temp.tenancy_tenantdomain VALUES (%s, 'evil.tenants.test', now())",
            [tid],
        )
        cur.execute("SET search_path = pg_temp, public")
        cur.execute("SELECT * FROM public.tenancy_resolve_host('evil.tenants.test')")
        assert cur.fetchall() == []
        conn.rollback()


def test_runtime_role_cannot_create_shadow_objects():
    for ddl in ("CREATE TEMP TABLE x (a int)", "CREATE TABLE public.x (a int)"):
        with pytest.raises(Exception, match="permission denied"), connection.cursor() as cursor:
            from django.db import transaction

            with transaction.atomic():
                cursor.execute(ddl)


# --------------------------------------------------------------------------- F2, F3
def test_f2_lists_only_the_users_open_memberships_of_resolvable_tenants(tenant_factory):
    me = make_user("me@example.com").user
    other = make_user("other@example.com").user
    expected = {}
    cases = [
        (TenantStatus.ACTIVE, "active", True),
        (TenantStatus.SUSPENDED, "invited", True),
        (TenantStatus.ACTIVE, "suspended", True),
        (TenantStatus.ACTIVE, "left", False),
        (TenantStatus.PROVISIONING, "active", False),
        (TenantStatus.DELETED, "active", False),
    ]
    for tenant_status, membership_status, visible in cases:
        ctx = tenant_factory(status=tenant_status)
        with tenant_atomic(ctx):
            m.Membership.objects.create(user=me, status=membership_status)
            m.Membership.objects.create(user=other, status="active")
        if visible:
            expected[ctx.id] = (ctx.slug, tenant_status, membership_status)
    rows = _one("SELECT * FROM public.tenancy_memberships_of(%s)", [me.pk])
    assert {r[0]: (r[1], r[3], r[4]) for r in rows} == expected
    assert _one("SELECT count(*) FROM public.tenancy_memberships_of(NULL)") == [(0,)]


def test_f3_lists_only_the_staff_members_own_sessions(tenant_factory):
    staff, other = make_user("staff@example.com").user, make_user("staff2@example.com").user
    ctx = tenant_factory()
    now = timezone.now()
    with tenant_atomic(ctx):
        mine = m.SupportSession.objects.create(
            staff_user=staff,
            reason="diagnose sync",
            ticket_ref="T-9",
            requested_at=now,
            starts_at=now,
            ends_at=now + timedelta(minutes=60),
            status="approved",
        )
        m.SupportSession.objects.create(
            staff_user=other, reason="other ticket", ticket_ref="T-8", requested_at=now
        )
    rows = _one("SELECT * FROM public.tenancy_support_sessions_of(%s)", [staff.pk])
    assert [(r[0], r[1], r[2], r[3]) for r in rows] == [(mine.pk, ctx.id, ctx.slug, "approved")]


# --------------------------------------------------------------------------- wrappers
def test_wrappers_run_only_inside_their_catalogued_operation(tenant_factory, admin):
    ctx = _tenant_with_domain(tenant_factory, TenantStatus.ACTIVE)
    host = f"{ctx.slug}.tenants.test"
    for call in (
        lambda: wrappers.resolve_host(host),
        wrappers.memberships_of,
        wrappers.support_sessions_of,
    ):
        with pytest.raises(PlatformScopeError, match="Only callable inside"):
            call()
    with platform_scope(operation="P2", actor=admin.user, reason="my institutions"):
        with pytest.raises(PlatformScopeError, match="P1"):
            wrappers.resolve_host(host)
    with platform_scope(operation="P1", actor=None, reason="host resolution"):
        assert wrappers.resolve_host(host) == wrappers.HostResolution(ctx.id, "active")
        assert wrappers.resolve_host("1.2.3.4") is None
        with pytest.raises(PlatformScopeError, match="P2"):
            wrappers.memberships_of()
    with tenant_atomic(ctx), pytest.raises(TenantContextConflict):
        with platform_scope(operation="P1", actor=None, reason="host resolution"):
            pass


def test_memberships_wrapper_uses_the_scope_actor_only(tenant_factory, admin):
    ctx = tenant_factory()
    with tenant_atomic(ctx):
        m.Membership.objects.create(user=admin.user, status="active")
        m.Membership.objects.create(user=make_user("x@example.com").user, status="active")
    with platform_scope(operation="P2", actor=admin.user, reason="my institutions"):
        result = wrappers.memberships_of()
    assert [(r.tenant_id, r.membership_status) for r in result] == [(ctx.id, "active")]


def test_support_sessions_wrapper_requires_p6_permission(tenant_factory, admin):
    """P6 needs ``tenancy.support_session.request`` (registered in M5), checked uncached: an
    account without it is refused; a Super Admin holds it. The wrapper returns the actor's own
    sessions only."""
    from django.core.exceptions import PermissionDenied

    from tests.helpers import make_user

    plain = make_user("plain-staff@example.com").user
    with pytest.raises(PermissionDenied):
        with platform_scope(operation="P6", actor=plain, reason="list my sessions"):
            pass
    ctx = tenant_factory()
    with tenant_atomic(ctx):
        m.SupportSession.objects.create(
            staff_user=admin.user,
            reason="diagnose import",
            ticket_ref="T-3",
            requested_at=timezone.now(),
        )
    with platform_scope(operation="P6", actor=admin.user, reason="list my sessions"):
        sessions = wrappers.support_sessions_of()
    assert [(s.tenant_id, s.status) for s in sessions] == [(ctx.id, "requested")]


def test_only_the_wrapper_module_calls_the_definer_functions():
    backend = Path(__file__).resolve().parents[3]
    pattern = re.compile(r"tenancy_(resolve_host|memberships_of|support_sessions_of)\s*\(")
    callers = []
    for path in (backend / "apps").rglob("*.py"):
        rel = path.relative_to(backend).as_posix()
        if "/tests/" in rel or "/migrations/" in rel:
            continue
        if pattern.search(path.read_text(encoding="utf-8")):
            callers.append(rel)
    assert callers == ["apps/tenancy/selectors/platform.py"]
