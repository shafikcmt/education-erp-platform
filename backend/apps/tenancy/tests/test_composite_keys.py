"""Composite foreign keys between tenant tables (Phase 3 M2; plan §4.4; ADR-044, Q8).

PostgreSQL foreign-key checks bypass row-level security. These tests prove that the composite
``(tenant_id, …)`` keys make cross-tenant (and cross-institution) references impossible in the
database itself, for the runtime role and for the owner, and that a foreign id fails exactly
like a random one (no existence oracle).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import psycopg
import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.core.ids import new_id
from apps.core.tenancy import TenantContext, tenant_atomic
from apps.rbac.models import Role
from apps.tenancy.models import Campus, Institution

pytestmark = pytest.mark.django_db

EXPECTED_FKS = {
    "tenancy_campus_institution_fk": (
        "tenancy_campus",
        ["tenant_id", "institution_id"],
        "tenancy_institution",
        ["tenant_id", "id"],
    ),
    "tenancy_invitation_role_fk": (
        "tenancy_invitation",
        ["tenant_id", "role_id"],
        "rbac_role",
        ["tenant_id", "id"],
    ),
    "tenancy_invitation_institution_fk": (
        "tenancy_invitation",
        ["tenant_id", "institution_id"],
        "tenancy_institution",
        ["tenant_id", "id"],
    ),
    "tenancy_invitation_campus_fk": (
        "tenancy_invitation",
        ["tenant_id", "institution_id", "campus_id"],
        "tenancy_campus",
        ["tenant_id", "institution_id", "id"],
    ),
}


def _fk_violation(sql: str, params: list[Any]) -> str:
    """Run ``sql`` in a savepoint and return the SQLSTATE of the failure ('' if none)."""
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql, params)
    except IntegrityError as exc:
        return getattr(exc.__cause__, "sqlstate", "") or "integrity"
    return ""


def _org(ctx: TenantContext, code: str = "main") -> tuple[Institution, Campus, Role]:
    with tenant_atomic(ctx):
        inst = Institution.objects.create(code=code, name=code, institution_type="school")
        campus = Campus.objects.create(
            institution=inst, code=f"{code}-c", name="Campus", is_main=True
        )
        # Tenant roles exist only inside their tenant (dual-scope RLS, M6).
        role = Role.objects.create(tenant_id=ctx.id, code=f"r-{code}", name="Role", kind="tenant")
    return inst, campus, role


INSERT_CAMPUS = (
    "INSERT INTO tenancy_campus (id, created_at, updated_at, tenant_id, institution_id, code, "
    "name, name_i18n, address, timezone, is_main) "
    "VALUES (%s, now(), now(), %s, %s, %s, 'x', '{}', '{}', '', false)"
)
INSERT_INVITE = (
    "INSERT INTO tenancy_invitation (id, created_at, updated_at, tenant_id, email, role_id, "
    "scope_type, institution_id, campus_id, token_hash, expires_at) "
    "VALUES (%s, now(), now(), %s, %s, %s, %s, %s, %s, %s, now() + interval '7 days')"
)


def _invite(ctx: TenantContext, role: Any, scope: str, inst: Any = None, campus: Any = None) -> str:
    return _fk_violation(
        INSERT_INVITE,
        [new_id(), ctx.id, "x@example.com", role, scope, inst, campus, uuid.uuid4().hex * 2],
    )


# --------------------------------------------------------------------------- catalogue
def test_composite_keys_exist_with_the_expected_shape():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT con.conname, src.relname, dst.relname, con.confmatchtype::text,
                   con.confdeltype::text, con.condeferrable,
              ARRAY(SELECT a.attname FROM unnest(con.conkey) WITH ORDINALITY k(n, o)
                    JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.n
                    ORDER BY k.o),
              ARRAY(SELECT a.attname FROM unnest(con.confkey) WITH ORDINALITY k(n, o)
                    JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k.n
                    ORDER BY k.o)
            FROM pg_constraint con
            JOIN pg_class src ON src.oid = con.conrelid JOIN pg_class dst ON dst.oid = con.confrelid
            WHERE con.contype = 'f' AND con.conname = ANY(%s)
            """,
            [list(EXPECTED_FKS)],
        )
        rows = {r[0]: r for r in cursor.fetchall()}
    assert set(rows) == set(EXPECTED_FKS)
    for name, (src, cols, dst, fcols) in EXPECTED_FKS.items():
        _, rsrc, rdst, match, delete, deferrable, rcols, rfcols = rows[name]
        assert (rsrc, rdst, rcols, rfcols) == (src, dst, cols, fcols), name
        assert (match, delete, deferrable) == ("s", "r", False), name  # SIMPLE, RESTRICT, immediate


def test_no_single_column_constraint_between_tenant_tables():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT con.conname FROM pg_constraint con
            JOIN pg_class src ON src.oid = con.conrelid JOIN pg_class dst ON dst.oid = con.confrelid
            WHERE con.contype = 'f' AND src.relname LIKE 'tenancy\\_%%'
              AND dst.relname IN ('tenancy_institution', 'tenancy_campus', 'rbac_role')
              AND array_length(con.conkey, 1) = 1
            """
        )
        assert cursor.fetchall() == []


# --------------------------------------------------------------------------- runtime role
def test_runtime_role_cannot_reference_another_tenants_rows(tenant_factory):
    a, b = tenant_factory(), tenant_factory()
    inst_a, campus_a, role_a = _org(a, "a")
    inst_b, campus_b, role_b = _org(b, "b")
    with tenant_atomic(a):
        # Campus under tenant B's institution.
        assert _fk_violation(INSERT_CAMPUS, [new_id(), a.id, inst_b.id, "x"]) == "23503"
        # Invitations to tenant B's role / institution / campus.
        assert _invite(a, role_b.id, "tenant") == "23503"
        assert _invite(a, role_a.id, "institution", inst_b.id) == "23503"
        assert _invite(a, role_a.id, "campus", inst_b.id, campus_b.id) == "23503"
        assert _invite(a, role_a.id, "campus", inst_a.id, campus_b.id) == "23503"
        # Control: own references are accepted.
        assert _invite(a, role_a.id, "campus", inst_a.id, campus_a.id) == ""


def test_campus_must_belong_to_the_invitations_institution(tenant_factory):
    a = tenant_factory()
    inst_1, campus_1, role = _org(a, "one")
    with tenant_atomic(a):
        inst_2 = Institution.objects.create(code="two", name="two", institution_type="college")
        assert _invite(a, role.id, "campus", inst_2.id, campus_1.id) == "23503"
        assert _invite(a, role.id, "campus", inst_1.id, campus_1.id) == ""


def test_template_and_platform_roles_can_never_be_referenced(tenant_factory):
    a = tenant_factory()
    template = Role.objects.filter(kind="template", tenant_id__isnull=True).first()
    platform = Role.objects.filter(kind="platform", tenant_id__isnull=True).first()
    assert template is not None and platform is not None
    with tenant_atomic(a):
        assert _invite(a, template.id, "tenant") == "23503"
        assert _invite(a, platform.id, "tenant") == "23503"


def test_foreign_id_fails_exactly_like_a_random_id(tenant_factory):
    """No existence oracle: B's real institution id and a random id give the same error."""
    a, b = tenant_factory(), tenant_factory()
    inst_b, _, _ = _org(b, "b")
    messages = []
    with tenant_atomic(a):
        for target in (inst_b.id, new_id()):
            try:
                with transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute(INSERT_CAMPUS, [new_id(), a.id, target, "x"])
            except IntegrityError as exc:
                cause = exc.__cause__
                messages.append((cause.sqlstate, cause.diag.constraint_name))  # type: ignore[union-attr]
    assert messages[0] == messages[1] == ("23503", "tenancy_campus_institution_fk")


def test_scope_check_requires_the_right_keys(tenant_factory):
    a = tenant_factory()
    inst, _campus, role = _org(a, "s")
    with tenant_atomic(a):
        assert _invite(a, role.id, "tenant", inst.id) == "23514"  # check violation
        assert _invite(a, role.id, "institution") == "23514"
        assert _invite(a, role.id, "campus", inst.id) == "23514"


def test_referenced_rows_cannot_be_deleted(tenant_factory):
    a = tenant_factory()
    inst, _, _ = _org(a, "d")
    with (
        tenant_atomic(a),
        pytest.raises(IntegrityError),
        transaction.atomic(),
        connection.cursor() as c,
    ):
        c.execute("DELETE FROM tenancy_institution WHERE id = %s", [inst.id])


# --------------------------------------------------------------------------- owner role
def test_owner_role_is_refused_too(owner_dsn):
    """FK checks bypass RLS for every role: the owner (FORCE RLS applies to it, but not to FK
    checks) still can't cross tenants. Everything runs in one owner transaction, rolled back."""
    a, b = new_id(), new_id()
    with psycopg.connect(**owner_dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT set_config('app.tenant_id', '', true)")
        for tid, slug in ((a, f"o{uuid.uuid4().hex[:12]}"), (b, f"o{uuid.uuid4().hex[:12]}")):
            cur.execute(
                "INSERT INTO tenancy_tenant (id, created_at, updated_at, slug, name, status, "
                "default_locale, locales, timezone, currency, country, data_region, limits, "
                "limits_override_reason, settings, branding) VALUES (%s, now(), now(), %s, 'x', "
                "'active', 'en', '{}', 'UTC', 'USD', '', '', '{}', '', '{}', '{}')",
                [tid, slug],
            )
        inst_b = new_id()
        cur.execute("SELECT set_config('app.tenant_id', %s, true)", [str(b)])
        cur.execute(
            "INSERT INTO tenancy_institution (id, created_at, updated_at, tenant_id, "
            "institution_type, code, name, name_i18n, preset_code, preset_version, settings) "
            "VALUES (%s, now(), now(), %s, 'school', 'b', 'b', '{}', '', '', '{}')",
            [inst_b, b],
        )
        cur.execute("SELECT set_config('app.tenant_id', %s, true)", [str(a)])
        cur.execute("SAVEPOINT s")
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            cur.execute(INSERT_CAMPUS, [new_id(), a, inst_b, "x"])
        conn.rollback()


def test_support_session_duration_and_read_only_checks(tenant_factory, admin):
    from apps.tenancy.models import SupportSession

    a = tenant_factory()
    now = timezone.now()
    with tenant_atomic(a):
        for minutes, ok in ((10, False), (15, True), (120, True), (121, False)):
            try:
                with transaction.atomic():
                    SupportSession.objects.create(
                        staff_user=admin.user,
                        reason="investigate ticket",
                        ticket_ref="T-1",
                        requested_at=now,
                        starts_at=now,
                        ends_at=now + timedelta(minutes=minutes),
                        status="ended",
                    )
                created = True
            except IntegrityError:
                created = False
            assert created is ok, minutes
        with pytest.raises(IntegrityError), transaction.atomic():
            SupportSession.objects.create(
                staff_user=admin.user,
                reason="x" * 10,
                ticket_ref="T",
                requested_at=now,
                access_level="read_write",
            )
