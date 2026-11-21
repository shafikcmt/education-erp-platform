"""Support sessions (Phase 3 M5; plan §11; ADR-045): S1-S10, R9, restricted owner mode (D2),
the approval setting (D5), emails, banner and history. Runs as ``erp_app`` through the real
middleware stack on tenant hosts."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.core.tenancy import tenant_atomic
from apps.identity.models import SessionRecord
from apps.rbac import tenant_roles
from apps.rbac.engine import ScopeTarget, effective_permissions
from apps.rbac.services import GuardRailViolation
from apps.rbac.sources import SELF_SERVICE_CODES as SELF
from apps.tenancy.models import SupportSession, Tenant
from apps.tenancy.rbac_sources import SupportSessionSource
from apps.tenancy.rules import TenantStatus
from apps.tenancy.selectors import support as support_selectors
from apps.tenancy.services import support
from tests.helpers import PASSWORD, Api, Person, make_user
from tests.isolation.factories import grant_role, seed_tenant_roles, tenant_events, tenant_host

DURABLE = "audit_durable"
pytestmark = pytest.mark.django_db(databases=["default", DURABLE])
READ = "/_probe/tenant-protected/"  # tenancy.member.view: support-readable
REVIEW = "/_probe/support-review/"  # tenancy.support_session.view: never support-readable
WRITE = "/_probe/tenant-write/"
READABLE = {
    "tenancy.tenant.view",
    "tenancy.institution.view",
    "tenancy.campus.view",
    "tenancy.member.view",
    "rbac.role.view",
    "rbac.assignment.view",
    "audit.event.view",
    "billing.subscription.view",  # Phase 4: the organisation's own subscription
}


@pytest.fixture
def staff(db) -> Person:
    return make_user("support@example.com", roles=("platform_support",), mfa=True)


def _request(
    org,
    staff: Person,
    minutes: int = 30,
    *,
    reason: str = "investigate failed imports",
    ticket_ref: str = "T-100",
) -> SupportSession:
    return support.request_session(
        actor=staff.user,
        tenant_id=org.tenant.id,
        reason=reason,
        ticket_ref=ticket_ref,
        minutes=minutes,
    )


def _approve(org, session: SupportSession, actor=None) -> SupportSession:
    with tenant_atomic(org.tenant):
        return support.approve_session(actor=actor or org.owner, session=session)


def _staff_api(org, staff: Person, *, step: int = 0) -> Api:
    api = Api(host=tenant_host(org.tenant))
    response = api.post("/api/v1/auth/login/", {"email": staff.user.email, "password": PASSWORD})
    assert response.status_code == 200, response.content
    assert response.json()["status"] == "mfa_required"
    verified = api.post("/api/v1/auth/mfa/verify/", {"code": staff.code(step)})
    assert verified.status_code == 200, verified.content
    return api


def _refused(org, person: Person) -> bool:
    response = Api(host=tenant_host(org.tenant)).post(
        "/api/v1/auth/login/", {"email": person.user.email, "password": person.password}
    )
    return (response.status_code, response.json()["code"]) == (401, "invalid_credentials")


def _events(org, action: str, *, durable: bool = False) -> list[AuditEvent]:
    return tenant_events(org.tenant, using=DURABLE if durable else "default", action=action)


def _session(org, pk) -> SupportSession:
    with tenant_atomic(org.tenant):
        return SupportSession.objects.get(pk=pk)


def _set_status(org, *statuses: str) -> None:
    row = Tenant.objects.get(pk=org.tenant.id)
    for status in statuses:
        row.status = status
        row.save()


# --------------------------------------------------------------------------- requesting
def test_a_request_needs_reason_ticket_bounded_length_and_the_p6_permission(org, staff):
    for kw in (
        {"reason": "too short"},
        {"ticket_ref": ""},
        {"ticket_ref": "x" * 65},
        {"minutes": 14},
        {"minutes": 121},
    ):
        with pytest.raises(ValidationError):
            _request(org, staff, **kw)
    with pytest.raises(PermissionDenied):  # an account without the platform permission
        _request(org, make_user("plain@example.com"))
    with pytest.raises(ValidationError):
        support.request_session(
            actor=staff.user, tenant_id=org.owner.pk, reason="x" * 20, ticket_ref="T", minutes=30
        )
    _request(org, staff)
    with pytest.raises(ValidationError, match="open support session"):
        _request(org, staff)
    with tenant_atomic(org.tenant):
        assert SupportSession.objects.count() == 1


def test_request_is_audited_in_both_logs_and_owners_are_asked(
    org, staff, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        session = _request(org, staff, minutes=45)
    assert (session.status, session.duration_minutes, session.starts_at) == ("requested", 45, None)
    platform = AuditEvent.objects.filter(
        tenant_id__isnull=True, action__startswith="platform.operation", actor_user_id=staff.user.pk
    )
    assert {e.metadata["operation"] for e in platform} == {"P6"}
    assert {e.action for e in platform} == {
        "platform.operation.started",
        "platform.operation.completed",
    }
    [event] = _events(org, "support.session.requested")
    assert (event.actor_type, event.support_session_id, event.metadata) == (
        "support",
        session.pk,
        {"minutes": 45, "auto_approved": False},
    )
    assert [m.to for m in mail.outbox] == [["owner@example.com"]]
    assert "needs your approval" in mail.outbox[0].subject
    assert "investigate failed imports" in mail.outbox[0].body


def test_with_approval_off_a_request_opens_at_once_but_stays_bounded(
    org, staff, django_capture_on_commit_callbacks
):
    with tenant_atomic(org.tenant):
        support.set_approval_required(
            actor=org.owner, required=False, reason="vendor contract signed"
        )
    with django_capture_on_commit_callbacks(execute=True):
        session = _request(org, staff, minutes=20)
    assert session.status == "approved" and session.approved_by is None
    assert session.ends_at and session.starts_at
    assert session.ends_at - session.starts_at == timedelta(minutes=20)
    assert "was opened" in mail.outbox[-1].subject
    with tenant_atomic(org.tenant):
        support.revoke_session(actor=org.owner, session=session)
    assert _session(org, session.pk).status == "revoked"


# --------------------------------------------------------------------------- using (S2, S3, S4)
def test_no_access_before_approval_read_only_access_after(
    org, staff, django_capture_on_commit_callbacks
):
    session = _request(org, staff)
    assert _refused(org, staff)  # D7: indistinguishable from a wrong password
    _approve(org, session)
    with django_capture_on_commit_callbacks(execute=True):
        api = _staff_api(org, staff)
        assert api.get(READ).status_code == 200
    assert _session(org, session.pk).status == "active"
    assert "has started" in mail.outbox[-1].subject
    # S3: never an approval or other non-readable code, never a write.
    denied = api.get(REVIEW)
    assert (denied.status_code, denied.json()["code"]) == (403, "permission_denied")
    write = api.post(WRITE)
    assert (write.status_code, write.json()["code"]) == (403, "support_access_read_only")
    assert api.patch("/api/v1/me/", {"full_name": "x"}).json()["code"] == (
        "support_access_read_only"
    )
    [rejected] = _events(org, "support.write_rejected", durable=True)
    assert (rejected.support_session_id, rejected.metadata) == (session.pk, {"method": "POST"})
    # S4: each successful support request is audited with the session id.
    requests = _events(org, "support.request")
    assert [(e.actor_type, e.support_session_id, e.metadata["path"]) for e in requests] == [
        ("support", session.pk, READ)
    ]
    with tenant_atomic(org.tenant):
        granted = effective_permissions(staff.user, ScopeTarget(org.tenant.id), use_cache=False)
    assert granted == SELF | READABLE


def test_a_session_exists_only_on_its_own_tenant(org, staff, tenant_site):
    """S2: a session approved for A gives nothing on B, through the host or under RLS."""
    other = tenant_site(slug="bravo")
    seed_tenant_roles(other)
    _approve(org, _request(org, staff))
    assert _refused(Namespace(tenant=other), staff)
    with tenant_atomic(other):
        assert SupportSessionSource().grants(staff.user, ScopeTarget(other.id)) == frozenset()
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM tenancy_supportsession")
            assert cursor.fetchone()[0] == 0
    # Outside any tenant transaction the source grants nothing either.
    assert SupportSessionSource().grants(staff.user, ScopeTarget(org.tenant.id)) == frozenset()


class Namespace:
    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


def test_r9_a_support_read_fails_without_its_audit_row(org, staff, monkeypatch):
    """S4 / R9: if the audit insert fails, the request fails and returns no data."""
    from apps.audit.services import record as real
    from apps.tenancy import middleware

    _approve(org, _request(org, staff))
    api = _staff_api(org, staff)

    def failing(action: str, **kw: Any) -> Any:
        if action == "support.request":
            raise RuntimeError("audit storage down")
        return real(action, **kw)

    monkeypatch.setattr(middleware, "audit", failing)
    response = api.get(READ)
    assert response.status_code == 500 and response.json()["code"] == "internal_error"
    assert b'"ok"' not in response.content
    monkeypatch.undo()
    assert api.get(READ).status_code == 200


# --------------------------------------------------------------------------- approval rules (S6)
def test_nobody_approves_their_own_or_without_the_permission(org, staff):
    session = _request(org, staff)
    with tenant_atomic(org.tenant), pytest.raises(PermissionDenied):
        support.approve_session(actor=staff.user, session=session)  # not a member
    with tenant_atomic(org.tenant), pytest.raises(PermissionDenied):
        support.approve_session(actor=org.head, session=session)  # no approve permission
    grant_role(org.tenant, staff.user, "tenant_owner")  # even an owner can't approve own
    with tenant_atomic(org.tenant), pytest.raises(GuardRailViolation) as exc:
        support.approve_session(actor=staff.user, session=session)
    assert exc.value.code == "cannot_act_on_self"
    with tenant_atomic(org.tenant):
        rejected = support.reject_session(actor=org.owner, session=session)
        assert rejected.status == "rejected"
        with pytest.raises(ValidationError):
            support.approve_session(actor=org.owner, session=session)


# --------------------------------------------------------------------------- ending (S7)
def test_revoke_takes_effect_at_once_and_ends_the_staff_host_sessions(org, staff):
    session = _approve(org, _request(org, staff))
    api = _staff_api(org, staff)
    elsewhere = Api()  # the same staff member on the platform host
    elsewhere.post("/api/v1/auth/login/", {"email": staff.user.email, "password": PASSWORD})
    assert elsewhere.post("/api/v1/auth/mfa/verify/", {"code": staff.code(1)}).status_code == 200
    assert api.get(READ).status_code == 200
    with tenant_atomic(org.tenant):
        support.revoke_session(actor=org.owner, session=session)
    records = {r.host: r for r in SessionRecord.objects.filter(user=staff.user)}
    assert records[tenant_host(org.tenant)].revoked_at is not None
    assert records["testserver"].revoked_at is None
    assert api.get(READ).status_code == 401
    assert elsewhere.get("/api/v1/me/").status_code == 200
    assert _refused(org, staff)


def test_an_expired_window_is_refused_and_expires_the_session(org, staff):
    session = _approve(org, _request(org, staff, minutes=15))
    api = _staff_api(org, staff)
    assert api.get(READ).status_code == 200
    past = timezone.now() - timedelta(hours=1)
    with tenant_atomic(org.tenant):
        SupportSession.objects.filter(pk=session.pk).update(
            starts_at=past - timedelta(minutes=15), ends_at=past
        )
    response = api.get(READ)
    assert (response.status_code, response.json()["code"]) == (403, "support_session_expired")
    assert _session(org, session.pk).status == "expired"  # committed by the follow-up
    assert (
        SessionRecord.objects.get(user=staff.user, host=tenant_host(org.tenant)).revoked_at
        is not None
    )
    assert [e.metadata for e in _events(org, "support.access_denied", durable=True)] == [
        {"reason": "support_session_expired"}
    ]


def test_staff_can_end_their_own_session(org, staff):
    session = _approve(org, _request(org, staff))
    api = _staff_api(org, staff)
    ended = support.end_session(actor=staff.user, tenant_id=org.tenant.id, session_id=session.pk)
    assert ended.status == "ended" and ended.ended_at is not None
    assert api.get(READ).status_code == 401
    with pytest.raises(ValidationError):  # someone else's session is "unknown"
        support.end_session(
            actor=make_user("x@example.com", roles=("platform_support",)).user,
            tenant_id=org.tenant.id,
            session_id=session.pk,
        )


# --------------------------------------------------------------------------- suspension (D2, S10)
def test_suspension_closes_support_and_leaves_owners_a_restricted_mode(org, staff):
    session = _approve(org, _request(org, staff))
    api = _staff_api(org, staff)
    owner_api = Api(host=tenant_host(org.tenant))
    # Owners are privileged accounts: they sign in with MFA (ADR-035).
    owner = make_user("second-owner@example.com", mfa=True)
    grant_role(org.tenant, owner.user, "tenant_owner")
    member = Person(user=org.teacher)
    _set_status(org, TenantStatus.SUSPENDED)
    # Staff: no data, no sign-in (S10), and the source grants nothing.
    assert api.get(READ).json()["code"] == "tenant_suspended"
    assert _refused(org, staff)
    with tenant_atomic(org.tenant):
        assert SupportSessionSource().grants(staff.user, ScopeTarget(org.tenant.id)) == frozenset()
        assert support.revoke_open_sessions(reason="tenant_suspended") == 1
    assert _session(org, session.pk).status == "revoked"
    # Members: only owners sign in, and only to the restricted-mode views.
    assert _refused(org, member)
    owner_api.login(owner, expect="authenticated")
    assert owner_api.get(REVIEW).status_code == 200
    assert owner_api.get(READ).json()["code"] == "tenant_suspended"
    assert owner_api.get("/api/v1/me/").json()["code"] == "tenant_suspended"
    # Requests may be made and reviewed while suspended, but can't be used.
    second = _request(org, staff)
    _approve(org, second)
    assert _refused(org, staff)
    assert owner_api.post("/api/v1/auth/logout/").status_code == 204
    _set_status(org, TenantStatus.ACTIVE)
    assert _staff_api(org, staff, step=1).get(READ).status_code == 200


# --------------------------------------------------------------------------- D5 setting
def test_only_an_owner_changes_the_approval_setting_and_it_is_audited(
    org, django_capture_on_commit_callbacks
):
    clone_holder = org.head
    with tenant_atomic(org.tenant):
        owner_like = tenant_roles.clone_role(
            actor=org.owner,
            tenant_id=org.tenant.id,
            source=tenant_roles.system_role(org.tenant.id, "tenant_owner"),  # in the tenant
            code="co-owner",
            name="Co-owner",
        )
    from apps.tenancy.models import Membership
    from apps.tenancy.services.assignments import create_assignment

    with tenant_atomic(org.tenant):
        create_assignment(
            membership=Membership.objects.get(user=clone_holder),
            role=owner_like,
            scope_type="tenant",
        )
        # Holds every owner permission through a clone, but is not an owner.
        with pytest.raises(PermissionDenied):
            support.set_approval_required(
                actor=clone_holder, required=False, reason="faster support please"
            )
        with pytest.raises(PermissionDenied):
            support.set_approval_required(
                actor=org.teacher, required=False, reason="faster support please"
            )
        with pytest.raises(ValidationError):
            support.set_approval_required(actor=org.owner, required=False, reason="short")
        assert (
            support.set_approval_required(actor=org.owner, required=True, reason="no change at all")
            is True
        )
    assert _events(org, "tenancy.support_approval.changed") == []
    with django_capture_on_commit_callbacks(execute=True), tenant_atomic(org.tenant):
        support.set_approval_required(
            actor=org.owner, required=False, reason="vendor contract signed"
        )
    [event] = _events(org, "tenancy.support_approval.changed")
    assert (event.actor_user_id, event.metadata) == (
        org.owner.pk,
        {"old": True, "new": False, "reason": "vendor contract signed"},
    )
    assert Tenant.objects.get(pk=org.tenant.id).settings["support_access_requires_approval"] is (
        False
    )
    assert "was changed" in mail.outbox[-1].subject and mail.outbox[-1].to == ["owner@example.com"]


# --------------------------------------------------------------------------- visibility (S5)
def test_banner_shows_usable_sessions_and_history_needs_the_view_permission(org, staff):
    with tenant_atomic(org.tenant):
        assert support_selectors.banner() == []
    session = _approve(org, _request(org, staff))
    with tenant_atomic(org.tenant):
        [row] = support_selectors.banner()
        assert (row["id"], row["status"], row["ticket_ref"]) == (session.pk, "approved", "T-100")
        history = support_selectors.history(actor=org.owner)
        assert [h["id"] for h in history] == [session.pk]
        assert history[0]["staff_user_id"] == staff.user.pk
        with pytest.raises(PermissionDenied):
            support_selectors.history(actor=org.teacher)


# --------------------------------------------------------------------------- K7
def test_k7_no_support_request_is_allowed_after_the_revoke_commits(committed_tenant_sites):
    """K7: the staff member's request loop runs while the tenant revokes the session in a
    real, committed transaction. Every request that STARTS after the commit is refused."""
    import threading
    import time

    from apps.identity.models import User
    from apps.rbac.models import RoleAssignment
    from apps.tenancy.models import Membership
    from tests.isolation.threads import in_thread

    tenant = committed_tenant_sites[0]
    org = Namespace(tenant=tenant)
    emails = (f"k7-owner-{tenant.slug}@example.com", f"k7-staff-{tenant.slug}@example.com")

    def setup() -> tuple[Any, Person]:
        seed_tenant_roles(tenant)
        owner = make_user(emails[0]).user
        grant_role(tenant, owner, "tenant_owner")
        staff = make_user(emails[1], roles=("platform_support",), mfa=True)
        session = _request(org, staff)
        with tenant_atomic(tenant):
            support.approve_session(actor=owner, session=session)
        return owner, staff

    owner, staff = in_thread(setup)
    stop = threading.Event()
    log: list[tuple[float, float, int]] = []
    errors: list[BaseException] = []

    def poller() -> None:
        from django.db import connections

        try:
            api = _staff_api(org, staff)
            while not stop.is_set():
                started = time.monotonic()
                status = api.get(READ).status_code
                log.append((started, time.monotonic(), status))
        except BaseException as exc:
            errors.append(exc)
        finally:
            connections.close_all()

    def revoke() -> float:
        with tenant_atomic(tenant):
            session = SupportSession.objects.get(staff_user=staff.user)
            support.revoke_session(actor=owner, session=session)
        return time.monotonic()

    def cleanup() -> None:
        with tenant_atomic(tenant):
            SupportSession.objects.all().delete()
            RoleAssignment.objects.all().delete()
            Membership.objects.all().delete()
        User.objects.filter(email__in=emails).delete()

    thread = threading.Thread(target=poller)
    thread.start()
    try:
        deadline = time.monotonic() + 30
        while len(log) < 20 and time.monotonic() < deadline and not errors:
            time.sleep(0.01)
        committed_at = in_thread(revoke)
        before = len(log)
        while len(log) < before + 20 and time.monotonic() < deadline + 30 and not errors:
            time.sleep(0.01)
    finally:
        stop.set()
        thread.join()
        in_thread(cleanup)
    assert errors == []
    earlier = [status for _, finished, status in log if finished < committed_at]
    after = [status for started, _, status in log if started > committed_at]
    assert len(earlier) >= 10 and set(earlier) == {200}
    assert len(after) >= 15 and 200 not in set(after), set(after)
