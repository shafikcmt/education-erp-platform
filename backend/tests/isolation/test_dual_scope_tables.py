"""Dual-scope RLS on the Phase 2 tables (Phase 3 M6; plan §5.1, §8.3 R2; ADR-046, D3).

``rbac_role`` / ``rbac_rolepermission`` (dual): platform rows readable everywhere, tenant rows
only in their tenant, writes only in the current scope. ``audit_auditevent`` /
``audit_auditeventip`` (private dual): the platform log and each tenant's log never see each
other. Raw SQL as ``erp_app`` throughout, so the database, not the ORM, is under test.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.db import connection, transaction
from django.db.utils import ProgrammingError
from django.test import RequestFactory

from apps.audit import services as audit
from apps.audit.models import AuditEvent, AuditEventIP
from apps.core.ids import new_id
from apps.core.tenancy import tenant_atomic
from apps.rbac.models import Permission, Role, RoleKind, RolePermission
from apps.tenancy.iteration import in_every_scope
from tests.helpers import make_user
from tests.isolation.factories import seed_tenant_roles, system_role

pytestmark = pytest.mark.django_db


def _rows(sql: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return list(cursor.fetchall())


def _request(ip: str = "203.0.113.9") -> Any:
    return RequestFactory().get("/", REMOTE_ADDR=ip)


# --------------------------------------------------------------------------- roles (dual)
def test_roles_platform_rows_everywhere_tenant_rows_only_at_home(tenant_factory):
    a, b = tenant_factory(), tenant_factory()
    seed_tenant_roles(a)
    seed_tenant_roles(b)
    platform_ids = {r[0] for r in _rows("SELECT id FROM rbac_role")}
    assert {r[0] for r in _rows("SELECT tenant_id FROM rbac_role")} == {None}
    with tenant_atomic(a):
        seen = _rows("SELECT DISTINCT tenant_id FROM rbac_role")
        assert {row[0] for row in seen} == {None, a.id}
        assert platform_ids <= {r[0] for r in _rows("SELECT id FROM rbac_role")}
        perms = {r[0] for r in _rows("SELECT DISTINCT tenant_id FROM rbac_rolepermission")}
        assert perms == {None, a.id}
    b_role = system_role(b, "teacher")
    with tenant_atomic(a):
        assert _rows("SELECT id FROM rbac_role WHERE id = %s", [b_role.pk]) == []


def test_role_writes_stay_in_their_scope(tenant_factory):
    a, b = tenant_factory(), tenant_factory()
    seed_tenant_roles(a)
    seed_tenant_roles(b)
    template = Role.objects.get(kind=RoleKind.TEMPLATE, code="teacher")
    perm = Permission.objects.get(code="tenancy.member.view")
    b_role = system_role(b, "teacher")
    with tenant_atomic(a):
        # A tenant can't change a template or a platform role ...
        assert (
            _rows("UPDATE rbac_role SET name = 'hijack' WHERE id = %s RETURNING id", [template.pk])
            == []
        )
        with pytest.raises(ProgrammingError, match="row-level security"), transaction.atomic():
            RolePermission.objects.create(role=template, permission=perm)
        # ... nor create a role for another tenant, nor touch one.
        with pytest.raises(ProgrammingError, match="row-level security"), transaction.atomic():
            Role.objects.create(tenant_id=b.id, code="x", name="X", kind=RoleKind.TENANT)
        assert (
            _rows("DELETE FROM rbac_rolepermission WHERE role_id = %s RETURNING id", [b_role.pk])
            == []
        )
    # The platform can't modify tenant roles (it can't even see them).
    assert _rows("UPDATE rbac_role SET name = 'x' WHERE id = %s RETURNING id", [b_role.pk]) == []
    assert Role.objects.get(pk=template.pk).name != "hijack"


# --------------------------------------------------------------------------- audit (private dual)
def test_r2_tenant_audit_events_are_invisible_everywhere_else(tenant_factory):
    """R2 (completed in M6): a tenant's events, durable or not, exist only in that tenant."""
    a, b = tenant_factory(), tenant_factory()
    platform_event = audit.record("identity.logout", request=_request())
    with tenant_atomic(a):
        a_event = audit.record("identity.logout", request=_request())
    with tenant_atomic(b):
        b_event = audit.record("identity.logout", request=_request())

    def visible() -> set[Any]:
        return {r[0] for r in _rows("SELECT id FROM audit_auditevent")}

    def visible_ips() -> set[Any]:
        return {r[0] for r in _rows("SELECT event_id FROM audit_auditeventip")}

    ids = {platform_event.pk, a_event.pk, b_event.pk}
    assert visible() & ids == {platform_event.pk}
    assert visible_ips() & ids == {platform_event.pk}
    with tenant_atomic(a):
        assert visible() & ids == {a_event.pk}
        assert visible_ips() & ids == {a_event.pk}
        # Forensic IP search on a tenant host finds only that tenant's events.
        assert set(audit.events_from_ip("203.0.113.9")) & ids == {a_event.pk}
    with tenant_atomic(b):
        assert visible() & ids == {b_event.pk}
    assert set(audit.events_from_ip("203.0.113.9")) & ids == {platform_event.pk}


def test_ip_rows_carry_their_events_tenant_and_it_never_moves(tenant_factory):
    a = tenant_factory()
    with tenant_atomic(a):
        event = audit.record("identity.logout", request=_request())
        assert _rows(
            "SELECT tenant_id FROM audit_auditeventip WHERE event_id = %s", [event.pk]
        ) == [(a.id,)]
        # Clearing (retention) is allowed and keeps the tenant; the column can't be rewritten.
        _rows(
            "UPDATE audit_auditeventip SET tenant_id = NULL, ip_encrypted = NULL, "
            "ip_index = NULL, anonymized_at = now() WHERE event_id = %s RETURNING event_id",
            [event.pk],
        )
        assert _rows(
            "SELECT tenant_id FROM audit_auditeventip WHERE event_id = %s", [event.pk]
        ) == [(a.id,)]
    platform = audit.record("identity.logout", request=_request())
    assert _rows("SELECT tenant_id FROM audit_auditeventip WHERE event_id = %s", [platform.pk]) == [
        (None,)
    ]


def test_nobody_writes_into_another_scopes_log(tenant_factory):
    a, b = tenant_factory(), tenant_factory()
    insert = (
        "INSERT INTO audit_auditevent (id, occurred_at, tenant_id, actor_type, action, outcome, "
        "target_type, target_id, metadata, user_agent_summary, request_id) "
        "VALUES (%s, now(), %s, 'system', 'identity.logout', 'success', '', '', '{}', '', '')"
    )
    with pytest.raises(ProgrammingError, match="row-level security"), transaction.atomic():
        _rows(insert + " RETURNING id", [new_id(), a.id])  # platform -> tenant log
    with tenant_atomic(a):
        for target in (b.id, None):  # tenant -> other tenant / platform log
            with pytest.raises(ProgrammingError, match="row-level security"), transaction.atomic():
                _rows(insert + " RETURNING id", [new_id(), target])
    with tenant_atomic(a), pytest.raises(ProgrammingError, match="permission denied"):
        # Append-only stays in force underneath RLS (no DELETE grant for the runtime role).
        with transaction.atomic():
            _rows("DELETE FROM audit_auditevent RETURNING id")


# --------------------------------------------------------------------------- P10 and erasure
def test_p10_and_erasure_cover_the_platform_and_every_tenant(tenant_factory, settings):
    a, b = tenant_factory(), tenant_factory()
    person = make_user("subject@example.com").user
    events = {"platform": audit.record("identity.logout", actor=person, request=_request())}
    for name, tenant in (("a", a), ("b", b)):
        with tenant_atomic(tenant):
            events[name] = audit.record("identity.logout", actor=person, request=_request())

    def state(name: str) -> tuple[bool, bool] | None:
        tenant = {"a": a, "b": b}.get(name)

        def read() -> tuple[bool, bool] | None:
            row = AuditEventIP.objects.filter(event=events[name]).first()
            if row is None:
                return None
            return row.ip_encrypted is None, row.anonymized_at is not None

        if tenant is None:
            return read()
        with tenant_atomic(tenant):
            return read()

    # Retention set to zero days: every stored IP is past it, in every scope.
    settings.SECURITY_IP_RETENTION_DAYS = 0
    without_iteration = audit.anonymize_expired_ips()  # the Phase 2 single pass
    assert state("platform") == (True, True) and without_iteration >= 1
    assert state("a") == state("b") == (False, False)  # invisible to a context-free pass
    totals = in_every_scope(
        audit.anonymize_expired_ips, operation="P10", reason="anonymise expired security-event IPs"
    )
    assert totals.failed == 0 and totals.tenant_rows >= 2
    assert state("a") == state("b") == (True, True)

    erased = in_every_scope(
        lambda: audit.erase_ips_for_actor(person.pk),
        operation="P13",
        reason="data-subject IP erasure",
    )
    assert erased.rows == 3 and erased.failed == 0
    assert state("platform") is None and state("a") is None and state("b") is None
    # Platform operation events record the run and the number of tenants it touched.
    completed = AuditEvent.objects.filter(
        action="platform.operation.completed", metadata__operation="P10"
    ).latest("occurred_at")
    assert completed.metadata["tenant_count"] >= 2


def test_scope_iteration_isolates_a_failing_tenant(tenant_factory):
    a, b = tenant_factory(), tenant_factory()
    calls: list[Any] = []

    def work() -> int:
        from apps.core.tenancy import current_tenant

        ctx = current_tenant()
        calls.append(ctx.id if ctx else None)
        if ctx is not None and ctx.id == a.id:
            raise RuntimeError("tenant A is broken")
        return 1

    totals = in_every_scope(work, operation="P10", reason="anonymise expired security-event IPs")
    assert calls[0] is None and a.id in calls and b.id in calls
    assert totals.failed == 1 and totals.platform == 1 and totals.tenant_rows == totals.tenants - 1
