"""Tenant-host API (Phase 3 M8; plan §12.1): allowed and denied per endpoint, scope filtering,
cross-tenant invisibility, limits and invitation acceptance over HTTP."""

from __future__ import annotations

from typing import Any

import pytest
from django.core import mail

from apps.core.tenancy import tenant_atomic
from apps.identity.models import User
from apps.tenancy.models import Campus, Institution, Membership
from tests.helpers import PASSWORD, Api, enroll_mfa, link_token, make_user
from tests.isolation.factories import (
    grant_role,
    seed_tenant_roles,
    system_role,
    tenant_events,
    tenant_host,
)

DURABLE = "audit_durable"
pytestmark = pytest.mark.django_db(databases=["default", DURABLE])
V1 = "/api/v1"


def _client(org: Any, user: User, *, step_up: bool = False) -> Api:
    person = enroll_mfa(user)
    api = Api(host=tenant_host(org.tenant))
    api.login(person, expect="authenticated")
    if step_up:
        api.step_up(person)
    return api


@pytest.fixture
def owner(org: Any) -> Api:
    return _client(org, org.owner, step_up=True)


@pytest.fixture
def head(org: Any) -> Api:
    return _client(org, org.head, step_up=True)


@pytest.fixture
def campus_admin(org: Any) -> Api:
    return _client(org, org.campus_admin)


@pytest.fixture
def teacher(org: Any) -> Api:
    api = Api(host=tenant_host(org.tenant))
    api.login(make_person(org.teacher), expect="authenticated")
    return api


def make_person(user: User) -> Any:
    from tests.helpers import Person

    return Person(user=user)


def _ids(response: Any) -> set[str]:
    assert response.status_code == 200, response.content
    return {row["id"] for row in response.json()}


# --------------------------------------------------------------------------- host classes
def test_tenant_routes_are_invisible_on_the_platform_host(org, admin_api):
    for path in ("/institutions/", "/tenant/", "/members/", "/public/tenant/", "/me/context/"):
        response = admin_api.get(V1 + path)
        assert response.status_code == 404, path
        assert response.json()["code"] == "not_found"


def test_public_tenant_data_is_minimal_and_anonymous(org):
    response = Api(host=tenant_host(org.tenant)).get(f"{V1}/public/tenant/")
    assert response.status_code == 200
    assert set(response.json()) == {"name", "default_locale", "locales", "branding"}
    assert response.json()["name"] == "ACME"


# --------------------------------------------------------------------------- profile
def test_profile_read_and_update_by_permission(org, owner, teacher):
    assert teacher.get(f"{V1}/tenant/").status_code == 200  # tenancy.tenant.view
    assert teacher.patch(f"{V1}/tenant/", {"name": "X"}).status_code == 403
    response = owner.patch(f"{V1}/tenant/", {"name": "ACME Schools", "locales": ["en", "bn"]})
    assert response.status_code == 200, response.content
    assert response.json()["name"] == "ACME Schools"
    assert "settings" not in response.json()
    [event] = tenant_events(org.tenant, action="tenancy.profile.updated")
    assert event.metadata == {"fields": "locales,name"}
    bad = owner.patch(f"{V1}/tenant/", {"default_locale": "ar"})
    assert bad.status_code == 400


def test_support_approval_setting_needs_an_owner_with_step_up(org, owner, head):
    body = {"requires_approval": False, "reason": "Support desk handles weekend incidents"}
    assert head.post(f"{V1}/tenant/support-approval/", body).status_code == 403
    response = owner.post(f"{V1}/tenant/support-approval/", body)
    assert response.status_code == 200, response.content
    assert response.json()["support_access_requires_approval"] is False


# --------------------------------------------------------------------------- institutions
def test_institution_lists_follow_the_actor_scopes(org, owner, head, campus_admin, teacher):
    north, south = str(org.north.pk), str(org.south.pk)
    assert _ids(owner.get(f"{V1}/institutions/")) == {north, south}
    assert _ids(head.get(f"{V1}/institutions/")) == {north}
    assert _ids(campus_admin.get(f"{V1}/institutions/")) == {north}  # through its campus
    assert teacher.get(f"{V1}/institutions/").status_code == 403
    assert head.get(f"{V1}/institutions/{south}/").status_code == 404
    assert head.patch(f"{V1}/institutions/{south}/", {"name": "x"}).status_code == 404
    response = head.patch(f"{V1}/institutions/{north}/", {"name": "North School"})
    assert response.status_code == 200 and response.json()["name"] == "North School"
    # A campus admin sees the institution but can't change it.
    assert campus_admin.patch(f"{V1}/institutions/{north}/", {"name": "y"}).status_code == 403


def test_institution_creation_respects_the_limit_until_overridden(org, owner, admin_api):
    body = {"code": "east", "name": "East", "institution_type": "college"}
    refused = owner.post(f"{V1}/institutions/", body)
    assert refused.status_code == 403
    assert refused.json()["code"] == "limit_exceeded"
    assert refused.json()["limit"] == 1
    override = admin_api.send(
        "put",
        f"{V1}/platform/tenants/{org.tenant.id}/limits/",
        {"max_institutions": 5, "max_campuses": 10, "reason": "Pilot with three schools"},
    )
    assert override.status_code == 200, override.content
    created = owner.post(f"{V1}/institutions/", body)
    assert created.status_code == 201, created.content
    assert owner.post(f"{V1}/institutions/", body).status_code == 400  # duplicate code


def test_archiving_an_institution_archives_its_campuses(org, owner, head):
    north = org.north.pk
    assert head.post(f"{V1}/institutions/{north}/archive/").status_code == 403  # not in template
    response = owner.post(f"{V1}/institutions/{north}/archive/")
    assert response.status_code == 200 and response.json()["archived_at"]
    with tenant_atomic(org.tenant):
        assert not Campus.objects.filter(institution_id=north, archived_at__isnull=True).exists()
    assert owner.patch(f"{V1}/institutions/{north}/", {"name": "z"}).status_code == 400


# --------------------------------------------------------------------------- campuses
def test_campus_scope_rules(org, owner, head, campus_admin):
    north, main, annex = org.north.pk, org.main.pk, org.annex.pk
    assert _ids(head.get(f"{V1}/institutions/{north}/campuses/")) == {str(main), str(annex)}
    assert _ids(campus_admin.get(f"{V1}/institutions/{north}/campuses/")) == {str(main)}
    assert campus_admin.get(f"{V1}/campuses/{annex}/").status_code == 404
    assert campus_admin.patch(f"{V1}/campuses/{main}/", {"name": "Main hall"}).status_code == 200
    # Moving "main" needs the permission at institution scope.
    assert campus_admin.patch(f"{V1}/campuses/{main}/", {"make_main": True}).status_code == 200
    refused = campus_admin.patch(f"{V1}/campuses/{main}/", {"name": "x"})
    assert refused.status_code == 200
    # The main campus can't be archived while another campus is open.
    assert head.post(f"{V1}/campuses/{main}/archive/").status_code == 400
    moved = head.patch(f"{V1}/campuses/{annex}/", {"make_main": True})
    assert moved.status_code == 200 and moved.json()["is_main"] is True
    assert head.post(f"{V1}/campuses/{main}/archive/").status_code == 200
    # Campus limit (3 per tenant): archived campuses don't count.
    created = head.post(f"{V1}/institutions/{north}/campuses/", {"code": "west", "name": "West"})
    assert created.status_code == 201, created.content
    full = head.post(f"{V1}/institutions/{north}/campuses/", {"code": "east", "name": "East"})
    assert full.status_code == 403 and full.json()["code"] == "limit_exceeded"
    assert owner.get(f"{V1}/campuses/{main}/").json()["archived_at"]


def test_another_tenants_objects_are_plain_404s(org, owner, tenant_site):
    other = tenant_site(slug="bravo")
    seed_tenant_roles(other)
    with tenant_atomic(other):
        foreign = Institution.objects.create(code="x", name="X", institution_type="school")
        foreign_campus = Campus.objects.create(institution=foreign, code="m", name="M")
    stranger = make_user("stranger@example.com").user
    grant_role(other, stranger, "teacher")
    for path in (
        f"/institutions/{foreign.pk}/",
        f"/institutions/{foreign.pk}/campuses/",
        f"/campuses/{foreign_campus.pk}/",
        f"/members/{_membership_id(other, stranger)}/",
        f"/roles/{system_role(other, 'teacher').pk}/",
    ):
        response = owner.get(V1 + path)
        assert response.status_code == 404, path
    assert owner.patch(f"{V1}/campuses/{foreign_campus.pk}/", {"name": "x"}).status_code == 404


def _membership_id(tenant: Any, user: User) -> Any:
    with tenant_atomic(tenant):
        return Membership.objects.get(user=user).pk


# --------------------------------------------------------------------------- members
def test_member_lists_and_lifecycle(org, owner, head, teacher):
    members = owner.get(f"{V1}/members/").json()
    assert {m["email"] for m in members} == {
        "owner@example.com",
        "head@example.com",
        "campus@example.com",
        "teacher@example.com",
    }
    visible = {m["email"] for m in head.get(f"{V1}/members/").json()}
    assert visible == {"head@example.com", "campus@example.com", "teacher@example.com"}
    assert teacher.get(f"{V1}/members/").status_code == 403
    teacher_id = _membership_id(org.tenant, org.teacher)
    owner_id = _membership_id(org.tenant, org.owner)
    assert head.get(f"{V1}/members/{owner_id}/").status_code == 404
    suspended = owner.patch(f"{V1}/members/{teacher_id}/", {"status": "suspended"})
    assert suspended.status_code == 200 and suspended.json()["status"] == "suspended"
    # Suspension ends the member's sessions on this host and the gate refuses the membership.
    assert teacher.get(f"{V1}/tenant/").json()["code"] == "not_authenticated"
    assert owner.patch(f"{V1}/members/{teacher_id}/", {"status": "active"}).status_code == 200
    # Owners can't remove themselves; the last owner rule holds.
    refused = owner.delete(f"{V1}/members/{owner_id}/")
    assert refused.status_code == 409 and refused.json()["code"] == "cannot_act_on_self"
    assert owner.delete(f"{V1}/members/{teacher_id}/").status_code == 204
    with tenant_atomic(org.tenant):
        assert Membership.objects.get(pk=teacher_id).status == "left"


def test_assignments_are_granted_in_scope_without_escalation(org, owner, head):
    teacher_id = _membership_id(org.tenant, org.teacher)
    url = f"{V1}/members/{teacher_id}/role-assignments/"
    before = head.get(url)
    assert before.status_code == 200 and len(before.json()) == 1
    coordinator = system_role(org.tenant, "academic_coordinator").pk
    owner_role = system_role(org.tenant, "tenant_owner").pk
    escalate = head.post(
        url,
        {"role": str(owner_role), "scope_type": "institution", "institution": str(org.north.pk)},
    )
    assert escalate.status_code == 403
    outside = head.post(
        url,
        {"role": str(coordinator), "scope_type": "institution", "institution": str(org.south.pk)},
    )
    assert outside.status_code == 403
    granted = owner.post(
        url,
        {"role": str(coordinator), "scope_type": "institution", "institution": str(org.north.pk)},
    )
    assert granted.status_code == 201, granted.content
    assignment = granted.json()["id"]
    assert owner.delete(f"{url}{assignment}/").status_code == 204
    assert {a["revoked_at"] is None for a in owner.get(url).json()} == {True, False}


# --------------------------------------------------------------------------- roles
def test_system_roles_are_read_only_and_clones_editable(org, owner, head):
    roles = owner.get(f"{V1}/roles/").json()
    teacher_role = next(r for r in roles if r["code"] == "teacher")
    assert teacher_role["is_system"] and teacher_role["template_code"] == "teacher"
    refused = owner.patch(f"{V1}/roles/{teacher_role['id']}/", {"name": "Lecturer"})
    assert refused.status_code == 409 and refused.json()["code"] == "system_role_read_only"
    no_clone = head.post(f"{V1}/roles/{teacher_role['id']}/clone/", {"code": "x_role", "name": "X"})
    assert no_clone.status_code == 403
    clone = owner.post(
        f"{V1}/roles/{teacher_role['id']}/clone/", {"code": "lecturer", "name": "Lecturer"}
    )
    assert clone.status_code == 201, clone.content
    clone_id = clone.json()["id"]
    updated = owner.patch(
        f"{V1}/roles/{clone_id}/", {"permissions": ["tenancy.tenant.view", "tenancy.member.view"]}
    )
    assert updated.status_code == 200, updated.content
    assert updated.json()["permissions"] == ["tenancy.member.view", "tenancy.tenant.view"]
    platform_code = owner.patch(
        f"{V1}/roles/{clone_id}/", {"permissions": ["tenancy.tenant.create"]}
    )
    assert platform_code.status_code == 403  # the owner doesn't hold it here
    assert owner.delete(f"{V1}/roles/{clone_id}/").status_code == 204
    assert owner.get(f"{V1}/roles/{clone_id}/").status_code == 404


# --------------------------------------------------------------------------- invitations
def test_invite_and_accept_with_a_new_account(org, owner, django_capture_on_commit_callbacks):
    role = system_role(org.tenant, "teacher").pk
    with django_capture_on_commit_callbacks(execute=True):
        created = owner.post(
            f"{V1}/invitations/",
            {
                "email": "new.teacher@example.com",
                "role": str(role),
                "scope_type": "campus",
                "institution": str(org.north.pk),
                "campus": str(org.main.pk),
            },
        )
    assert created.status_code == 201, created.content
    assert "token" not in created.json()
    token = link_token(mail.outbox[-1], "accept-invitation")
    anonymous = Api(host=tenant_host(org.tenant))
    missing_password = anonymous.post(f"{V1}/auth/invitations/accept/", {"token": token})
    assert missing_password.status_code == 400
    accepted = anonymous.post(
        f"{V1}/auth/invitations/accept/",
        {"token": token, "password": PASSWORD, "display_name": "New Teacher"},
    )
    assert accepted.status_code == 200, accepted.content
    assert accepted.json()["account_created"] is True
    user = User.objects.get(email="new.teacher@example.com")
    assert user.email_verified_at and user.check_password(PASSWORD)
    again = anonymous.post(f"{V1}/auth/invitations/accept/", {"token": token, "password": PASSWORD})
    assert again.status_code == 400 and again.json()["code"] == "invitation_invalid"
    # The new member can sign in on this host.
    member = Api(host=tenant_host(org.tenant))
    assert member.login(make_person(user)) == "authenticated"


def test_existing_accounts_accept_with_their_password(
    org, owner, django_capture_on_commit_callbacks, settings
):
    existing = make_user("known@example.com")
    role = system_role(org.tenant, "teacher").pk
    with django_capture_on_commit_callbacks(execute=True):
        owner.post(
            f"{V1}/invitations/",
            {"email": "known@example.com", "role": str(role), "scope_type": "tenant"},
        )
    token = link_token(mail.outbox[-1], "accept-invitation")
    anonymous = Api(host=tenant_host(org.tenant))
    url = f"{V1}/auth/invitations/accept/"
    limit = settings.SECURITY_THROTTLES["invite_accept"][0]
    for _ in range(limit):
        wrong = anonymous.post(url, {"token": token, "password": "not-my-password"})
        assert wrong.status_code == 401 and wrong.json()["code"] == "invalid_credentials"
    locked = anonymous.post(url, {"token": token, "password": PASSWORD})
    assert locked.status_code == 429
    reasons = [
        e.metadata["reason"]
        for e in tenant_events(
            org.tenant, using=DURABLE, action="tenancy.invitation.invalid_attempt"
        )
    ]
    assert reasons == ["bad_credentials"] * limit
    from django.core.cache import cache

    cache.clear()
    accepted = anonymous.post(url, {"token": token, "password": PASSWORD})
    assert accepted.status_code == 200, accepted.content
    assert accepted.json()["account_created"] is False
    assert User.objects.filter(email="known@example.com").count() == 1
    with tenant_atomic(org.tenant):
        assert Membership.objects.get(user=existing.user).status == "active"
    unknown = anonymous.post(url, {"token": "nope", "password": PASSWORD})
    assert unknown.status_code == 400 and unknown.json()["code"] == "invitation_invalid"


def test_invitation_management_is_scoped(org, owner, head):
    role = system_role(org.tenant, "teacher").pk
    south = owner.post(
        f"{V1}/invitations/",
        {
            "email": "s@example.com",
            "role": str(role),
            "scope_type": "institution",
            "institution": str(org.south.pk),
        },
    ).json()["id"]
    assert south not in _ids(head.get(f"{V1}/invitations/"))
    assert head.delete(f"{V1}/invitations/{south}/").status_code == 404
    assert head.post(f"{V1}/invitations/{south}/resend/").status_code == 404
    assert owner.post(f"{V1}/invitations/{south}/resend/").status_code == 200
    assert owner.delete(f"{V1}/invitations/{south}/").status_code == 204
    assert south not in _ids(owner.get(f"{V1}/invitations/"))


# --------------------------------------------------------------------------- context, audit
def test_context_lists_scopes_and_permissions(org, head):
    context = head.get(f"{V1}/me/context/").json()
    assert context["membership_status"] == "active"
    assert context["is_support_session"] is False
    scopes = {(s["scope_type"], s["institution"]) for s in context["scopes"]}
    assert ("institution", str(org.north.pk)) in scopes
    north = next(s for s in context["scopes"] if s["scope_type"] == "institution")
    assert "tenancy.campus.create" in north["permissions"]
    assert [a["role_code"] for a in context["assignments"]] == ["institution_admin"]


def test_tenant_audit_log_shows_only_this_tenant(org, owner, tenant_site):
    owner.patch(f"{V1}/tenant/", {"name": "Renamed"})
    other = tenant_site(slug="bravo")
    with tenant_atomic(other):
        from apps.audit.services import record

        record("tenancy.member.suspended")
    events = owner.get(f"{V1}/audit-events/").json()["results"]
    assert events and all(e["action"] != "tenancy.member.suspended" for e in events)
    assert "tenancy.profile.updated" in {e["action"] for e in events}


# --------------------------------------------------------------------------- MFA on tenant hosts
def test_me_reports_the_tenant_mfa_requirement_in_any_scope(org):
    """An institution admin holds privileged codes only in their institution, yet MFA is
    required on this tenant's host (and not for a teacher); the platform host is unaffected."""
    host = tenant_host(org.tenant)
    head = Api(host=host)
    head.login(make_person(org.head))
    me = head.get(f"{V1}/me/").json()
    assert (me["mfa_required"], me["mfa_enrollment_required"]) == (True, True)
    blocked = head.get(f"{V1}/institutions/")
    assert blocked.status_code == 403 and blocked.json()["code"] == "mfa_enrollment_required"
    teacher = Api(host=host)
    teacher.login(make_person(org.teacher))
    assert teacher.get(f"{V1}/me/").json()["mfa_required"] is False
    platform = Api()
    platform.login(make_person(org.head))
    assert platform.get(f"{V1}/me/").json()["mfa_required"] is False


def test_turning_mfa_off_is_not_served_on_tenant_hosts(org, owner):
    """Only enrolment and status are served on tenant hosts (plan N81). Turning MFA off on the
    platform host is possible for an account without platform roles, but every privileged
    tenant request then needs a new enrolment (the gate above)."""
    assert owner.delete(f"{V1}/me/mfa/totp/").status_code == 404
    assert owner.get(f"{V1}/me/mfa/").json() | {"confirmed_at": None} == {
        "enabled": True,
        "is_required": True,
        "confirmed_at": None,
        "recovery_codes_remaining": 0,
    }
