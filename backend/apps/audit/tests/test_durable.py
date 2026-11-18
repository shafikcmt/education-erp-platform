"""Durable security audit (Phase 3 M3; plan §8.3, tests R2-R4 and L6; ADR-042).

Real transactions: everything runs in a worker thread on unwrapped connections, with
committed tenants. Audit rows are append-only, so each test finds its own events by tenant id.

R2 is covered here only as far as M3 can prove it: the durable event carries the right
``tenant_id``. Invisibility from other tenants needs the dual-scope RLS of M6.
"""

from __future__ import annotations

import pytest
from django.db import connections

from apps.audit import services
from apps.audit.events import DURABLE_ACTIONS
from apps.audit.models import AuditEvent
from apps.core.tenancy import tenant_atomic
from apps.core.tenancy.exceptions import TenantContextNotApplied
from tests.isolation.threads import in_thread
from tests.isolation_app.models import ProbeRecord

DURABLE = "audit_durable"
# Listing the alias lets the worker threads open their own (unwrapped) durable connection.
pytestmark = pytest.mark.django_db(databases=["default", DURABLE])


class _BoomError(Exception):
    pass


def _events(tenant, **filters):
    def read() -> list[AuditEvent]:
        with tenant_atomic(tenant):
            return list(AuditEvent.objects.filter(**filters))

    return in_thread(read)


def test_durable_event_survives_the_rollback_and_plain_events_do_not(committed_tenant_pair):
    """R1 at the service level, R2 (tenant id) and R3."""
    tenant, other = committed_tenant_pair

    def run() -> dict[str, object]:
        seen: dict[str, object] = {}
        try:
            with tenant_atomic(tenant):
                ProbeRecord.objects.create(name="uncommitted")
                services.record("identity.logout")  # an ordinary, in-transaction event
                event = services.record(
                    "authz.denied",
                    outcome="denied",
                    metadata={"permission": "x.y.z", "reason": "missing_permission"},
                )
                seen["event"] = event.pk
                # R3: the durable connection is another transaction; it can't see our row.
                with tenant_atomic(tenant, using=DURABLE):
                    seen["durable_sees"] = ProbeRecord.objects.using(DURABLE).count()
                seen["main_sees"] = ProbeRecord.objects.count()
                # L6: applying the tenant on ``default`` never applies it on the other alias.
                with pytest.raises(TenantContextNotApplied):
                    ProbeRecord.objects.using(DURABLE).count()
                raise _BoomError
        except _BoomError:
            pass
        with tenant_atomic(tenant):
            seen["rows_after"] = ProbeRecord.objects.count()
        return seen

    seen = in_thread(run)
    assert (seen["durable_sees"], seen["main_sees"], seen["rows_after"]) == (0, 1, 0)
    events = _events(tenant)
    assert [(e.action, e.pk) for e in events] == [("authz.denied", seen["event"])]
    assert events[0].tenant_id == tenant.id and events[0].outcome == "denied"
    assert _events(other) == []


def test_explicit_durable_flag_and_default_tenant_stamp(committed_tenant_pair):
    tenant, _ = committed_tenant_pair

    def run() -> None:
        try:
            with tenant_atomic(tenant):
                services.record("identity.logout", durable=True)
                services.record("identity.password.changed")
                raise _BoomError
        except _BoomError:
            pass
        with tenant_atomic(tenant):
            services.record("identity.password.changed")  # committed with its transaction

    in_thread(run)
    assert sorted(e.action for e in _events(tenant)) == [
        "identity.logout",
        "identity.password.changed",
    ]


def test_durable_write_failure_never_raises_and_is_logged(committed_tenant_pair, caplog):
    """R4: the durable database is unreachable. The caller (a denial path) continues and the
    failure is logged with the action; no event is stored."""
    tenant, _ = committed_tenant_pair

    def run() -> object:
        conn = connections[DURABLE]
        conn.close()
        port = conn.settings_dict["PORT"]
        conn.settings_dict["PORT"] = "1"  # connection refused
        try:
            with tenant_atomic(tenant):
                event = services.record(
                    "authz.denied", outcome="denied", metadata={"permission": "", "reason": "x"}
                )
                # The request transaction is still usable after the failed durable write.
                ProbeRecord.objects.create(name="still-works")
                return event._state.adding
        finally:
            conn.settings_dict["PORT"] = port
            with tenant_atomic(tenant):
                ProbeRecord.objects.all().delete()

    assert in_thread(run) is True  # an unsaved placeholder was returned
    assert _events(tenant) == []
    assert "audit.durable_write_failed" in caplog.text


def test_outside_a_tenant_context_nothing_changes(db):
    """Platform behaviour (Phase 2): in the caller's transaction, failures propagate."""
    event = services.record(
        "authz.denied", outcome="denied", metadata={"permission": "a.b.c", "reason": "r"}
    )
    assert event.tenant_id is None
    assert AuditEvent.objects.filter(pk=event.pk).exists()  # same (test) transaction
    with pytest.raises(ValueError, match="Unknown audit action"):
        services.record("not.an.event")


def test_durable_set_holds_only_denials_and_failures():
    assert {
        "authz.denied",
        "identity.login.failed",
        "identity.login.locked",
        "identity.login.throttled",
        "identity.mfa.challenge_failed",
        "identity.mfa.locked",
        "support.access_denied",
        "support.write_rejected",
        "tenancy.invitation.invalid_attempt",
        "tenancy.isolation.blocked",
    } == DURABLE_ACTIONS
    assert not any("succeeded" in action for action in DURABLE_ACTIONS)
