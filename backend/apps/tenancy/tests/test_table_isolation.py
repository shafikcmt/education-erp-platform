"""Raw-SQL isolation of every tenancy tenant table as ``erp_app`` (Phase 3 M2; plan §15.2).

For each table: tenant A sees only its own rows, cannot see/update/delete B's rows by id,
cannot insert or move a row into B, and without a tenant context nothing is visible. The ORM
manager agrees.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from apps.core.ids import new_id
from apps.core.tenancy import TenantContext, tenant_atomic
from apps.rbac.models import Role
from apps.tenancy import models as m
from tests.helpers import make_user

pytestmark = pytest.mark.django_db


def _domain(ctx: TenantContext) -> Any:
    return m.TenantDomain.objects.create(domain=f"{ctx.slug}.tenants.test", is_primary=True)


def _institution(ctx: TenantContext) -> Any:
    return m.Institution.objects.create(code="main", name="Main", institution_type="school")


def _campus(ctx: TenantContext) -> Any:
    inst = m.Institution.objects.create(code="c-inst", name="I", institution_type="madrasa")
    return m.Campus.objects.create(institution=inst, code="main", name="Main", is_main=True)


def _membership(ctx: TenantContext) -> Any:
    return m.Membership.objects.create(user=make_user(f"{ctx.slug}@example.com").user)


def _invitation(ctx: TenantContext) -> Any:
    role = Role.objects.create(tenant_id=ctx.id, code=f"r{ctx.slug}", name="R", kind="tenant")
    return m.Invitation.objects.create(
        email=f"{ctx.slug}@example.com",
        role=role,
        scope_type="tenant",
        token_hash=uuid.uuid4().hex * 2,
        expires_at=timezone.now() + timedelta(days=7),
    )


def _support(ctx: TenantContext) -> Any:
    return m.SupportSession.objects.create(
        staff_user=make_user(f"staff-{ctx.slug}@example.com").user,
        reason="diagnose ticket",
        ticket_ref="T-1",
        requested_at=timezone.now(),
    )


TABLES: dict[str, tuple[Any, Callable[[TenantContext], Any]]] = {
    "tenancy_tenantdomain": (m.TenantDomain, _domain),
    "tenancy_institution": (m.Institution, _institution),
    "tenancy_campus": (m.Campus, _campus),
    "tenancy_membership": (m.Membership, _membership),
    "tenancy_invitation": (m.Invitation, _invitation),
    "tenancy_supportsession": (m.SupportSession, _support),
}
UNIQUE_OVERRIDES = {"domain": "forged.tenants.test", "token_hash": "f" * 64}


def _rows(sql: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return list(cursor.fetchall())


def _rowcount(sql: str, params: list[Any]) -> int:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return int(cursor.rowcount)


def _rls_denied(sql: str, params: list[Any]) -> bool:
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql, params)
    except DatabaseError as exc:
        return "row-level security" in str(exc)
    return False


@pytest.mark.parametrize("table", sorted(TABLES))
def test_tenant_table_is_isolated(table, tenant_factory):
    model, build = TABLES[table]
    a, b = tenant_factory(), tenant_factory()
    with tenant_atomic(a):
        row_a = build(a)
    with tenant_atomic(b):
        row_b = build(b)

    with tenant_atomic(a):
        ids = {r[0] for r in _rows(f"SELECT id FROM {table}")}
        assert ids == {row_a.pk}
        assert _rows(f"SELECT id FROM {table} WHERE id = %s", [row_b.pk]) == []
        assert _rowcount(f"UPDATE {table} SET updated_at = now() WHERE id = %s", [row_b.pk]) == 0
        assert _rowcount(f"DELETE FROM {table} WHERE id = %s", [row_b.pk]) == 0
        # Moving A's row into B, or inserting a copy owned by B, is rejected by RLS.
        assert _rls_denied(f"UPDATE {table} SET tenant_id = %s WHERE id = %s", [b.id, row_a.pk])
        overlay = {"id": str(new_id()), "tenant_id": str(b.id)}
        overlay |= {k: v for k, v in UNIQUE_OVERRIDES.items() if hasattr(row_a, k)}
        assert _rls_denied(
            f"INSERT INTO {table} SELECT * FROM jsonb_populate_record(NULL::{table}, "
            f"(SELECT to_jsonb(x) || %s::jsonb FROM {table} x WHERE x.id = %s))",
            [json.dumps(overlay), row_a.pk],
        )
        assert list(model.objects.values_list("pk", flat=True)) == [row_a.pk]

    # No tenant context: nothing is visible (fail closed).
    assert _rows(f"SELECT count(*) FROM {table}") == [(0,)]
    with tenant_atomic(b):
        assert {r[0] for r in _rows(f"SELECT id FROM {table}")} == {row_b.pk}


def test_every_tenancy_tenant_table_is_covered():
    tenant_tables = {
        model._meta.db_table
        for model in (
            m.TenantDomain,
            m.Institution,
            m.Campus,
            m.Membership,
            m.Invitation,
            m.SupportSession,
        )
    }
    assert tenant_tables == set(TABLES)
