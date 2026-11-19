"""Platform-host tenancy API (Phase 3 M8; plan §12.2; P2, P4, P5, P6, P8)."""

from __future__ import annotations

from typing import Any

import pytest
from django.core import mail

from apps.audit.models import AuditEvent
from apps.core.tenancy import tenant_atomic
from apps.rbac import tenant_roles
from apps.tenancy.models import (
    Campus,
    Institution,
    Invitation,
    SupportSession,
    Tenant,
    TenantDomain,
)
from apps.tenancy.rules import TenantStatus
from tests.helpers import Api, enroll_mfa, link_token, make_user
from tests.isolation.factories import add_member, tenant_events, tenant_host

DURABLE = "audit_durable"
pytestmark = pytest.mark.django_db(databases=["default", DURABLE])
V1 = "/api/v1"
TENANTS = f"{V1}/platform/tenants/"


def _provision_body(slug: str = "delta", **extra: Any) -> dict[str, Any]:
    return {
        "slug": slug,
        "name": "Delta Academy",
        "owner_email": "Owner@Delta.example.com",
        "default_locale": "bn",
        "locales": ["bn", "en"],
        "timezone": "Asia/Dhaka",
        "currency": "BDT",
        "country": "BD",
        "institution": {"institution_type": "madrasa", "code": "main", "name": "Delta Madrasa"},
        **extra,
    }


def _staff(email: str, *roles: str, step_up: bool = True) -> Api:
    person = make_user(email, roles=roles, mfa=True)
    api = Api()
    api.login(person, expect="authenticated")
    if step_up:
        api.step_up(person)
    return api


# --------------------------------------------------------------------------- P4
def test_provisioning_creates_a_working_tenant(admin_api, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = admin_api.post(TENANTS, _provision_body())
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == "active" and body["slug"] == "delta"
    assert body["limits"] == {"max_institutions": 1, "max_campuses": 3}
    assert "settings" not in body and "branding" not in body
    tenant = Tenant.objects.get(slug="delta").as_context()
    with tenant_atomic(tenant):
        [domain] = TenantDomain.objects.all()
        assert (domain.domain, domain.is_primary) == ("delta.tenants.test", True)
        assert domain.verified_at is not None
        [institution] = Institution.objects.all()
        assert institution.institution_type == "madrasa"
        [campus] = Campus.objects.all()
        assert campus.is_main and campus.institution_id == institution.pk
        [invitation] = Invitation.objects.select_related("role")
        assert invitation.email == "owner@delta.example.com"
        assert (invitation.role.code, invitation.scope_type) == ("tenant_owner", "tenant")
        assert tenant_roles.tenant_roles(tenant.id).filter(is_system=True).count() == 18
    assert "delta.tenants.test" in mail.outbox[-1].body
    assert link_token(mail.outbox[-1], "accept-invitation")
    [tenant_log] = tenant_events(tenant, action="tenancy.tenant.provisioned")
    assert tenant_log.metadata == {"slug": "delta"}
    platform = AuditEvent.objects.filter(tenant_id__isnull=True)
    assert platform.filter(action="tenancy.tenant.provisioned", target_id=tenant.id).exists()
    completed = platform.filter(action="platform.operation.completed").latest("occurred_at")
    assert completed.metadata["operation"] == "P4" and completed.metadata["tenant_count"] == 1


def test_provisioning_is_refused_without_permission_and_for_bad_input(admin_api):
    plain = _staff("plain@example.com")
    assert plain.post(TENANTS, _provision_body()).status_code == 403
    support = _staff("support@example.com", "platform_support")
    assert support.post(TENANTS, _provision_body()).status_code == 403
    onboarding = _staff("onboarding@example.com", "platform_onboarding")
    assert onboarding.post(TENANTS, _provision_body("echo")).status_code == 201
    assert admin_api.post(TENANTS, _provision_body("echo")).status_code == 400  # slug taken
    for slug in ("admin", "a", "Bad_Slug", "x--y"):
        assert admin_api.post(TENANTS, _provision_body(slug)).status_code == 400, slug
    no_country = admin_api.post(TENANTS, _provision_body("golf", country=""))
    assert no_country.status_code == 201, no_country.content
    mismatch = _provision_body("foxtrot", default_locale="ar")
    assert admin_api.post(TENANTS, mismatch).status_code == 400
    assert not Tenant.objects.filter(slug="foxtrot").exists()


def test_provisioning_is_refused_while_tenant_hosts_are_disabled_where_required(
    admin_api, settings
):
    settings.TENANT_PROVISIONING_REQUIRES_HOSTS = True
    settings.TENANT_HOSTS_ENABLED = False
    response = admin_api.post(TENANTS, _provision_body())
    assert response.status_code == 409 and response.json()["code"] == "tenant_hosts_disabled"
    assert not Tenant.objects.filter(slug="delta").exists()


def test_a_failed_provisioning_leaves_a_tombstone_and_nothing_else(admin_api, monkeypatch):
    from apps.tenancy.services import registry

    def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("role copy failed")

    monkeypatch.setattr(registry, "sync_system_copies", boom)
    client = Api()
    client.client = admin_api.client
    client.client.raise_request_exception = False
    response = client.post(TENANTS, _provision_body())
    assert response.status_code == 500
    tenant = Tenant.objects.get(slug="delta")
    assert tenant.status == TenantStatus.DELETED
    with tenant_atomic(tenant.as_context()):
        assert not TenantDomain.objects.exists() and not Institution.objects.exists()
    failed = AuditEvent.objects.get(action="tenancy.tenant.provisioning_failed")
    assert failed.metadata["error"] == "RuntimeError" and failed.outcome == "failure"
    # The slug stays taken (tombstone).
    monkeypatch.undo()
    assert admin_api.post(TENANTS, _provision_body()).status_code == 400


# --------------------------------------------------------------------------- P8 / P5
def test_registry_list_and_detail_show_registry_fields_only(admin_api, tenant_factory):
    tenant_factory(slug="alpha")
    tenant_factory(slug="bravo", status=TenantStatus.SUSPENDED)
    gone = tenant_factory(slug="gamma")
    Tenant.objects.filter(pk=gone.id).update(status=TenantStatus.OFFBOARDING)
    Tenant.objects.filter(pk=gone.id).update(status=TenantStatus.DELETED)
    rows = admin_api.get(TENANTS).json()["results"]
    assert [r["slug"] for r in rows] == ["alpha", "bravo"]
    assert all("settings" not in r for r in rows)
    assert [r["slug"] for r in admin_api.get(TENANTS, status="suspended").json()["results"]] == [
        "bravo"
    ]
    assert [r["slug"] for r in admin_api.get(TENANTS, q="alp").json()["results"]] == ["alpha"]
    assert admin_api.get(f"{TENANTS}{gone.id}/").status_code == 404
    assert _staff("plain@example.com").get(TENANTS).status_code == 403
    assert _staff("sup@example.com", "platform_support").get(TENANTS).status_code == 200


def test_registry_update_writes_both_logs(admin_api, tenant_factory):
    tenant = tenant_factory(slug="alpha")
    response = admin_api.patch(f"{TENANTS}{tenant.id}/", {"name": "Alpha Group", "country": "BD"})
    assert response.status_code == 200, response.content
    assert response.json()["name"] == "Alpha Group"
    [event] = tenant_events(tenant, action="tenancy.tenant.updated")
    assert event.metadata["fields"] == "country,name"
    assert AuditEvent.objects.filter(
        tenant_id__isnull=True, action="tenancy.tenant.updated", target_id=tenant.id
    ).exists()
    assert admin_api.patch(f"{TENANTS}{tenant.id}/", {"settings": {}}).status_code == 200
    assert Tenant.objects.get(pk=tenant.id).settings == {"support_access_requires_approval": True}


def test_suspension_needs_step_up_and_revokes_support_access(admin, tenant_site):
    tenant = tenant_site(slug="acme")
    member = make_user("member@example.com")
    add_member(tenant, member.user)
    staff = make_user("staff@example.com", roles=("platform_support",), mfa=True)
    with tenant_atomic(tenant):
        from django.utils import timezone

        SupportSession.objects.create(
            staff_user=staff.user,
            reason="Investigating a fee report",
            ticket_ref="T-1",
            requested_at=timezone.now(),
        )
    no_step_up = Api()
    no_step_up.login(admin, expect="authenticated")
    reason = {"reason": "Unpaid subscription for 90 days"}
    refused = no_step_up.post(f"{TENANTS}{tenant.id}/suspend/", reason)
    assert refused.status_code == 403 and refused.json()["code"] == "step_up_required"
    no_step_up.step_up(admin)
    assert no_step_up.post(f"{TENANTS}{tenant.id}/suspend/", {"reason": "short"}).status_code == 400
    response = no_step_up.post(f"{TENANTS}{tenant.id}/suspend/", reason)
    assert response.status_code == 200 and response.json()["status"] == "suspended"
    with tenant_atomic(tenant):
        assert SupportSession.objects.get().status == "revoked"
    [event] = tenant_events(tenant, action="tenancy.tenant.suspended")
    assert event.metadata["reason"] == reason["reason"]
    platform_event = AuditEvent.objects.get(
        tenant_id__isnull=True, action="tenancy.tenant.suspended"
    )
    assert platform_event.metadata["revoked_support_count"] == 1
    # Members are refused from now on.
    blocked = Api(host=tenant_host(tenant)).post(
        f"{V1}/auth/login/", {"email": member.user.email, "password": member.password}
    )
    assert blocked.status_code == 401
    assert no_step_up.post(f"{TENANTS}{tenant.id}/suspend/", reason).status_code == 400
    back = no_step_up.post(f"{TENANTS}{tenant.id}/reactivate/", reason)
    assert back.status_code == 200 and back.json()["status"] == "active"


def test_limit_override_is_audited_and_validated(admin_api, tenant_factory):
    tenant = tenant_factory(slug="alpha")
    url = f"{TENANTS}{tenant.id}/limits/"
    bad = admin_api.send("put", url, {"max_institutions": 0, "max_campuses": 2, "reason": "x" * 12})
    assert bad.status_code == 400
    ok = admin_api.send(
        "put", url, {"max_institutions": 4, "max_campuses": 12, "reason": "Signed contract #42"}
    )
    assert ok.status_code == 200 and ok.json()["limits"] == {
        "max_institutions": 4,
        "max_campuses": 12,
    }
    row = Tenant.objects.get(pk=tenant.id)
    assert row.limits_override_reason == "Signed contract #42" and row.limits_overridden_by
    [event] = tenant_events(tenant, action="tenancy.tenant.limits_overridden")
    assert event.metadata["max_campuses"] == 12


def test_owner_invitation_can_be_replaced(
    admin_api, tenant_site, django_capture_on_commit_callbacks
):
    tenant = tenant_site(slug="acme")
    from tests.isolation.factories import seed_tenant_roles

    seed_tenant_roles(tenant)
    url = f"{TENANTS}{tenant.id}/owner-invitation/"
    with django_capture_on_commit_callbacks(execute=True):
        assert admin_api.post(url, {"email": "boss@example.com"}).status_code == 202
        assert admin_api.post(url, {"email": "boss@example.com"}).status_code == 202
    with tenant_atomic(tenant):
        open_ones = Invitation.objects.filter(revoked_at__isnull=True, accepted_at__isnull=True)
        assert open_ones.count() == 1
    assert len(mail.outbox) == 2


# --------------------------------------------------------------------------- P2
def test_my_memberships_on_the_platform_host(tenant_site):
    tenant = tenant_site(slug="acme")
    other = tenant_site(slug="bravo")
    person = make_user("member@example.com")
    add_member(tenant, person.user)
    add_member(other, person.user, status="suspended")
    api = Api()
    api.login(person, expect="authenticated")
    rows = {r["slug"]: r for r in api.get(f"{V1}/me/memberships/").json()}
    assert set(rows) == {"acme", "bravo"}
    assert rows["acme"]["membership_status"] == "active"
    assert rows["acme"]["sign_in_url"] == "http://acme.tenants.test:8080/"
    assert rows["bravo"]["membership_status"] == "suspended"
    # Tenant hosts never serve it.
    assert Api(host=tenant_host(tenant)).get(f"{V1}/me/memberships/").status_code == 404


# --------------------------------------------------------------------------- P6
def test_support_staff_request_list_and_end_their_sessions(tenant_site):
    tenant = tenant_site(slug="acme")
    support = _staff("support@example.com", "platform_support")
    body = {
        "tenant": str(tenant.id),
        "reason": "Report generation fails for class 7",
        "ticket_ref": "SUP-77",
        "minutes": 30,
    }
    created = support.post(f"{V1}/platform/support-sessions/", body)
    assert created.status_code == 201, created.content
    session_id = created.json()["session_id"]
    assert created.json()["status"] == "requested"
    [row] = support.get(f"{V1}/platform/support-sessions/").json()
    assert (row["session_id"], row["tenant_slug"]) == (session_id, "acme")
    assert support.post(f"{V1}/platform/support-sessions/", body).status_code == 400  # one open
    plain = _staff("plain@example.com")
    assert plain.post(f"{V1}/platform/support-sessions/", body).status_code == 403
    assert plain.post(f"{V1}/platform/support-sessions/{session_id}/end/").status_code == 403
    other_staff = _staff("other@example.com", "platform_support")
    assert other_staff.post(f"{V1}/platform/support-sessions/{session_id}/end/").status_code == 404
    ended = support.post(f"{V1}/platform/support-sessions/{session_id}/end/")
    assert ended.status_code == 200 and ended.json()["status"] == "ended"


def test_tenant_owners_decide_support_requests_over_http(tenant_site):
    from tests.isolation.factories import grant_role, seed_tenant_roles

    tenant = tenant_site(slug="acme")
    seed_tenant_roles(tenant)
    owner_user = make_user("owner@example.com").user
    grant_role(tenant, owner_user, "tenant_owner")
    support = _staff("support@example.com", "platform_support")
    body = {
        "tenant": str(tenant.id),
        "reason": "Fee receipts are wrong",
        "ticket_ref": "S-9",
        "minutes": 15,
    }
    session_id = support.post(f"{V1}/platform/support-sessions/", body).json()["session_id"]
    owner_person = enroll_mfa(owner_user)
    owner = Api(host=tenant_host(tenant))
    owner.login(owner_person, expect="authenticated")
    assert [s["id"] for s in owner.get(f"{V1}/support-sessions/").json()] == [session_id]
    refused = owner.post(f"{V1}/support-sessions/{session_id}/approve/")
    assert refused.status_code == 403 and refused.json()["code"] == "step_up_required"
    owner.step_up(owner_person)
    approved = owner.post(f"{V1}/support-sessions/{session_id}/approve/")
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    revoked = owner.post(f"{V1}/support-sessions/{session_id}/revoke/")
    assert revoked.status_code == 200 and revoked.json()["status"] == "revoked"
