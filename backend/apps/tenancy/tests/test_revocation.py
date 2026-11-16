"""Revocation is effective on the next request (Phase 3 M4; plan §9.6, §15.3 K5).

Through the real middleware stack on tenant hosts: tenant permissions reach a view, and
revoking an assignment, suspending or removing a member takes effect immediately."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from apps.core.tenancy import tenant_atomic
from apps.identity.models import SessionRecord, User
from apps.rbac.models import RoleAssignment
from apps.tenancy.models import Membership
from apps.tenancy.services import assignments, memberships
from tests.helpers import Api, make_user
from tests.isolation.factories import grant_role, seed_tenant_roles, tenant_host
from tests.isolation.threads import in_thread

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])
PROTECTED = "/_probe/tenant-protected/"
PEOPLE: dict[Any, Any] = {}


def _api(org, email: str, template: str) -> tuple[Api, User]:
    # Administrative tenant roles are privileged: the account needs MFA (ADR-035).
    person = make_user(email, mfa=template != "teacher")
    PEOPLE[person.user.pk] = person
    grant_role(org.tenant, person.user, template)
    api = Api(host=tenant_host(org.tenant))
    api.login(person, expect="authenticated")
    return api, person.user


def test_tenant_permissions_reach_views_on_the_tenant_host(org):
    admin, _ = _api(org, "deputy@example.com", "institution_admin")
    teacher, _ = _api(org, "plain@example.com", "teacher")
    assert admin.get(PROTECTED).status_code == 200
    denied = teacher.get(PROTECTED)
    assert (denied.status_code, denied.json()["code"]) == (403, "permission_denied")
    # The same account has no such permission on the platform host.
    platform = Api()
    platform.login(make_user("p@example.com"), expect="authenticated")
    assert platform.get(PROTECTED).status_code == 404


def test_revoking_an_assignment_takes_effect_on_the_next_request(org):
    api, user = _api(org, "deputy@example.com", "institution_admin")
    assert api.get(PROTECTED).status_code == 200  # fills the permission cache
    with tenant_atomic(org.tenant):
        assignment = RoleAssignment.objects.get(membership__user=user)
        assignments.revoke_assignment(actor=org.owner, assignment=assignment)
    assert api.get(PROTECTED).status_code == 403
    assert api.get("/api/v1/me/").status_code == 200  # still a member


@pytest.mark.parametrize("action", ["suspend", "remove"])
def test_suspension_and_removal_end_tenant_sessions_only(org, action):
    api, user = _api(org, "deputy@example.com", "institution_admin")
    elsewhere = Api()  # the same person's session on the platform host
    person = PEOPLE[user.pk]
    elsewhere.post("/api/v1/auth/login/", {"email": user.email, "password": person.password})
    # A later TOTP step: the one used on the tenant host can't be replayed.
    verified = elsewhere.post("/api/v1/auth/mfa/verify/", {"code": person.code(1)})
    assert verified.status_code == 200, verified.content
    assert api.get(PROTECTED).status_code == 200
    with tenant_atomic(org.tenant):
        membership = Membership.objects.get(user=user)
        service = memberships.suspend_member if action == "suspend" else memberships.remove_member
        service(actor=org.owner, membership=membership)
    records = {r.host: r for r in SessionRecord.objects.filter(user=user)}
    assert records[tenant_host(org.tenant)].revoked_at is not None
    assert records[tenant_host(org.tenant)].revoke_reason.startswith("membership_")
    assert records["testserver"].revoked_at is None
    assert api.get(PROTECTED).status_code == 401  # the tenant session is gone
    assert elsewhere.get("/api/v1/me/").status_code == 200
    # Signing in again on the tenant host is refused like a wrong password (D7).
    again = Api(host=tenant_host(org.tenant)).post(
        "/api/v1/auth/login/", {"email": user.email, "password": PEOPLE[user.pk].password}
    )
    assert (again.status_code, again.json()["code"]) == (401, "invalid_credentials")


def test_k5_no_request_is_allowed_after_the_revoke_commits(committed_tenant_sites):
    """K5: one thread polls a protected endpoint while another revokes the assignment in a
    real, committed transaction. Every request that STARTS after the commit is denied."""
    tenant = committed_tenant_sites[0]
    email = f"k5-{tenant.slug}@example.com"

    def setup() -> Any:
        seed_tenant_roles(tenant)
        person = make_user(email, mfa=True)
        grant_role(tenant, person.user, "institution_admin")
        return person

    person = in_thread(setup)
    stop = threading.Event()
    log: list[tuple[float, float, int]] = []
    errors: list[BaseException] = []

    def poller() -> None:
        from django.db import connections

        try:
            api = Api(host=tenant_host(tenant))
            api.login(person, expect="authenticated")
            while not stop.is_set():
                started = time.monotonic()
                status = api.get(PROTECTED).status_code
                log.append((started, time.monotonic(), status))
        except BaseException as exc:
            errors.append(exc)
        finally:
            connections.close_all()

    def revoke() -> float:
        with tenant_atomic(tenant):
            assignment = RoleAssignment.objects.get(membership__user__email=email)
            assignments.end_assignments(
                RoleAssignment.objects.filter(pk=assignment.pk), revoked_by=None
            )
        return time.monotonic()  # the transaction has committed

    def cleanup() -> None:
        with tenant_atomic(tenant):
            RoleAssignment.objects.all().delete()
            Membership.objects.all().delete()
        User.objects.filter(email=email).delete()

    thread = threading.Thread(target=poller)
    thread.start()
    try:
        deadline = time.monotonic() + 20
        while len(log) < 20 and time.monotonic() < deadline and not errors:
            time.sleep(0.01)
        committed_at = in_thread(revoke)
        before = len(log)
        while len(log) < before + 20 and time.monotonic() < deadline + 20 and not errors:
            time.sleep(0.01)
    finally:
        stop.set()
        thread.join()
        in_thread(cleanup)
    assert errors == []
    after = [status for started, _, status in log if started > committed_at]
    earlier = [status for _, finished, status in log if finished < committed_at]
    assert len(earlier) >= 20 and set(earlier) == {200}
    assert len(after) >= 15 and set(after) == {403}, set(after)
