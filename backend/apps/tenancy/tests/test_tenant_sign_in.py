"""Sign-in on a tenant host (Phase 3 M3; plan §10.5, decision D7).

A non-member, an unknown email, a wrong password, an inactive membership and any sign-in on a
suspended tenant must be indistinguishable to the client: same status, body and counters.
Only the (durable) audit log knows the real reason.
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.audit.models import AuditEvent
from apps.identity import throttling
from apps.identity.models import SessionRecord
from apps.tenancy.rules import TenantStatus
from tests.helpers import PASSWORD, Api, make_user
from tests.isolation.factories import add_member, tenant_host

DURABLE = "audit_durable"
pytestmark = pytest.mark.django_db(databases=["default", DURABLE])


def _login(tenant, email: str, password: str = PASSWORD) -> Any:
    return Api(host=tenant_host(tenant)).post(
        "/api/v1/auth/login/", {"email": email, "password": password}
    )


def _shape(response: Any) -> tuple[int, dict[str, Any], str]:
    body = response.json()
    body.pop("request_id")
    return response.status_code, body, response["Content-Type"]


def _reasons(tenant) -> list[str]:
    events = AuditEvent.objects.using(DURABLE).filter(
        tenant_id=tenant.id, action="identity.login.failed"
    )
    return sorted(e.metadata["reason"] for e in events)


def test_every_refusal_looks_like_a_wrong_password(tenant_site):
    tenant = tenant_site(slug="acme")
    member = make_user("member@example.com")
    add_member(tenant, member.user)
    outsider = make_user("outsider@example.com")
    staff = make_user("root@example.com", roles=("super_admin",), mfa=True)
    for status in ("invited", "suspended", "left"):
        add_member(tenant, make_user(f"{status}@example.com").user, status=status)

    reference = _shape(_login(tenant, member.user.email, "wrong-password"))
    assert reference[0] == 401 and reference[1]["code"] == "invalid_credentials"
    attempts = {
        "unknown email": _login(tenant, "nobody@example.com"),
        "non-member": _login(tenant, outsider.user.email),
        "platform staff (non-member, MFA enrolled)": _login(tenant, staff.user.email),
        "invited": _login(tenant, "invited@example.com"),
        "suspended membership": _login(tenant, "suspended@example.com"),
        "left": _login(tenant, "left@example.com"),
    }
    for label, response in attempts.items():
        assert _shape(response) == reference, label
        assert "sessionid" not in response.cookies, label
    # A non-member with MFA never reaches the MFA step (it would be an oracle).
    assert not SessionRecord.objects.exclude(user=member.user).exists()
    assert _reasons(tenant) == sorted(
        ["invalid_credentials"] * 2 + ["not_a_member"] * 2 + ["membership_inactive"] * 3
    )
    # The same credentials work where they are valid.
    assert _login(tenant, member.user.email).status_code == 200
    assert (
        Api()
        .post("/api/v1/auth/login/", {"email": outsider.user.email, "password": PASSWORD})
        .status_code
        == 200
    )


def test_refusals_count_against_the_same_throttles(tenant_site, settings):
    tenant = tenant_site(slug="acme")
    outsider = make_user("outsider@example.com")
    api = Api(host=tenant_host(tenant))
    limit = throttling.Bucket.named("login_ip").limit
    statuses = [
        api.post(
            "/api/v1/auth/login/", {"email": outsider.user.email, "password": PASSWORD}
        ).status_code
        for _ in range(limit + 3)
    ]
    assert statuses[0] == 401 and statuses[-1] == 429
    assert set(statuses) == {401, 429}


def test_suspended_tenant_refuses_every_sign_in_generically(tenant_site):
    from apps.tenancy.models import Tenant

    tenant = tenant_site(slug="acme")
    member = make_user("member@example.com")
    add_member(tenant, member.user)
    reference = _shape(_login(tenant, member.user.email, "wrong-password"))
    row = Tenant.objects.get(pk=tenant.id)
    row.status = TenantStatus.SUSPENDED
    row.save()
    assert _shape(_login(tenant, member.user.email)) == reference
    assert "tenant_suspended" in _reasons(tenant)


def test_member_sign_in_creates_a_host_bound_session(tenant_site):
    a, b = tenant_site(slug="acme"), tenant_site(slug="bravo")
    person = make_user("teacher@example.com")
    add_member(a, person.user)
    api = Api(host=tenant_host(a))
    assert api.login(person) == "authenticated"
    assert SessionRecord.objects.get(user=person.user).host == tenant_host(a)
    # The same account is not a member of B: its own host refuses the same credentials.
    assert _login(b, person.user.email).status_code == 401
    succeeded = AuditEvent.objects.filter(action="identity.login.succeeded", tenant_id=a.id)
    assert succeeded.count() == 1
