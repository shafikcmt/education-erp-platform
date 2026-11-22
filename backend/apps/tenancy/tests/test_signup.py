"""Self-service sign-up (Phase 5 M8; ADR-060 Q3; P23 request/verify, P4 approval, P25 purge).

Off by default; enumeration-safe; throttled; honeypot; single-use hashed tokens with a 48-hour
expiry; every tenant needs a platform administrator's approval.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.core import mail
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.tenancy.models import SignupRequest, Tenant
from apps.tenancy.services.signup import purge_closed
from tests.helpers import Api, link_token, make_user

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])
V1 = "/api/v1"
SIGNUP, VERIFY, ADMIN = f"{V1}/signup/", f"{V1}/signup/verify/", f"{V1}/platform/signups/"


def _body(slug: str = "echo", email: str = "head@echo.example.com", **extra: Any) -> dict:
    return {
        "email": email,
        "organisation_name": "Echo Foundation",
        "slug": slug,
        "institution_type": "school",
        "institution_name": "Echo School",
        "default_locale": "bn",
        "timezone": "Asia/Dhaka",
        "currency": "BDT",
        "country": "BD",
        **extra,
    }


@pytest.fixture
def enabled(settings):
    settings.TENANCY_SIGNUP_ENABLED = True
    return settings


def _submit(api: Api, body: dict, callbacks) -> Any:
    with callbacks(execute=True):
        return api.post(SIGNUP, body)


def test_sign_up_is_off_by_default_and_reveals_nothing():
    anon = Api()
    assert anon.get(SIGNUP).json() == {"enabled": False}
    assert anon.post(SIGNUP, _body()).status_code == 404
    assert anon.post(SIGNUP, {}).status_code == 404  # no validation before the flag check
    assert anon.post(VERIFY, {"token": "x" * 43}).status_code == 404
    assert not SignupRequest.objects.exists() and not mail.outbox


def test_request_verify_approve_provisions_a_tenant_and_invites_the_owner(
    enabled, admin_api, django_capture_on_commit_callbacks
):
    anon = Api()
    assert anon.get(SIGNUP).json() == {"enabled": True}
    response = _submit(anon, _body(), django_capture_on_commit_callbacks)
    assert response.status_code == 202, response.content
    row = SignupRequest.objects.get()
    assert (row.status, row.email, row.slug) == ("pending", "head@echo.example.com", "echo")
    assert timedelta(hours=47) < row.expires_at - timezone.now() <= timedelta(hours=48)
    [message] = mail.outbox
    assert message.to == ["head@echo.example.com"] and "Echo Foundation" in message.subject
    token = link_token(message, "signup/verify")
    assert "/bn/signup/verify#token=" in message.body  # the requester's language
    assert row.token_hash != token and token not in str(row.__dict__)  # only the hash is stored
    event = AuditEvent.objects.get(action="tenancy.signup.requested")
    assert "head@echo" not in str(event.metadata)  # the email is never logged

    assert anon.post(VERIFY, {"token": token}).status_code == 200
    assert anon.post(VERIFY, {"token": token}).status_code == 400  # single use
    row.refresh_from_db()
    assert row.status == "verified" and row.verified_at is not None

    listing = admin_api.get(ADMIN, status="verified").json()
    assert [r["slug"] for r in listing] == ["echo"]
    with django_capture_on_commit_callbacks(execute=True):
        approved = admin_api.post(f"{ADMIN}{row.pk}/approve/")
    assert approved.status_code == 201, approved.content
    tenant = Tenant.objects.get(slug="echo")
    assert (tenant.name, tenant.default_locale, tenant.currency) == ("Echo Foundation", "bn", "BDT")
    assert tenant.locales == ["bn", "en"]
    row.refresh_from_db()
    assert (row.status, row.provisioned_tenant_id) == ("approved", tenant.pk)
    assert link_token(mail.outbox[-1], "accept-invitation")  # the owner invitation
    assert mail.outbox[-1].to == ["head@echo.example.com"]
    again = admin_api.post(f"{ADMIN}{row.pk}/approve/")
    assert again.status_code == 400  # approved at most once
    assert AuditEvent.objects.filter(action="tenancy.signup.approved").count() == 1


def test_responses_do_not_reveal_existing_accounts(enabled, django_capture_on_commit_callbacks):
    make_user("taken@example.com")
    anon = Api()
    first = _submit(
        anon, _body(slug="foxtrot", email="taken@example.com"), django_capture_on_commit_callbacks
    )
    second = _submit(
        anon, _body(slug="golf", email="new@example.com"), django_capture_on_commit_callbacks
    )
    assert (first.status_code, first.json()) == (second.status_code, second.json())


def test_honeypot_and_per_email_limit_are_silent(enabled, django_capture_on_commit_callbacks):
    anon = Api()
    bot = _submit(anon, _body(website="https://spam.example"), django_capture_on_commit_callbacks)
    assert bot.status_code == 202 and not SignupRequest.objects.exists() and not mail.outbox
    for i in range(4):
        response = _submit(
            Api(remote_addr=f"203.0.113.{i}"),
            _body(slug=f"hotel{i}"),
            django_capture_on_commit_callbacks,
        )
        assert response.status_code == 202
    assert SignupRequest.objects.count() == 3  # signup_email: 3 per day, then silent


def test_per_ip_limit_answers_429(enabled, django_capture_on_commit_callbacks):
    anon = Api()
    for i in range(5):
        assert (
            _submit(
                anon,
                _body(slug=f"india{i}", email=f"a{i}@example.com"),
                django_capture_on_commit_callbacks,
            ).status_code
            == 202
        )
    assert anon.post(SIGNUP, _body(slug="india9", email="z@example.com")).status_code == 429


def test_invalid_details_are_refused(enabled, tenant_factory):
    tenant_factory(slug="juliet")
    anon = Api()
    assert "slug" in str(anon.post(SIGNUP, _body(slug="juliet")).content)  # taken
    assert anon.post(SIGNUP, _body(slug="www")).status_code == 400  # reserved
    assert anon.post(SIGNUP, _body(slug="kilo", timezone="Mars/Olympus")).status_code == 400
    assert anon.post(SIGNUP, _body(slug="kilo", default_locale="xx")).status_code == 400
    assert not SignupRequest.objects.exists()


def test_expired_links_fail_and_the_purge_keeps_requests_awaiting_a_decision(
    enabled, admin_api, django_capture_on_commit_callbacks
):
    anon = Api()
    _submit(anon, _body(slug="lima", email="l@example.com"), django_capture_on_commit_callbacks)
    _submit(anon, _body(slug="mike", email="m@example.com"), django_capture_on_commit_callbacks)
    lima_token = link_token(mail.outbox[0], "signup/verify")
    mike_token = link_token(mail.outbox[1], "signup/verify")
    SignupRequest.objects.filter(slug="lima").update(
        expires_at=timezone.now() - timedelta(minutes=1)
    )
    assert anon.post(VERIFY, {"token": lima_token}).status_code == 400
    assert anon.post(VERIFY, {"token": mike_token}).status_code == 200
    statuses = {r["slug"]: r["status"] for r in admin_api.get(ADMIN).json()}
    assert statuses == {"lima": "expired", "mike": "verified"}
    old = timezone.now() - timedelta(days=31)
    SignupRequest.objects.update(created_at=old)
    assert purge_closed() == 1
    assert list(SignupRequest.objects.values_list("slug", flat=True)) == ["mike"]


def test_rejection_needs_a_reason_and_closes_the_request(
    enabled, admin_api, django_capture_on_commit_callbacks
):
    _submit(Api(), _body(slug="november"), django_capture_on_commit_callbacks)
    row = SignupRequest.objects.get()
    assert admin_api.post(f"{ADMIN}{row.pk}/reject/", {"reason": "short"}).status_code == 400
    rejected = admin_api.post(
        f"{ADMIN}{row.pk}/reject/", {"reason": "Duplicate of an existing customer"}
    )
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    assert admin_api.post(f"{ADMIN}{row.pk}/approve/").status_code == 400
    assert not Tenant.objects.filter(slug="november").exists()


def test_a_failed_provisioning_leaves_the_request_verified(
    enabled, admin_api, tenant_factory, django_capture_on_commit_callbacks
):
    anon = Api()
    _submit(anon, _body(slug="oscar"), django_capture_on_commit_callbacks)
    anon.post(VERIFY, {"token": link_token(mail.outbox[0], "signup/verify")})
    tenant_factory(slug="oscar")  # someone took the name meanwhile
    row = SignupRequest.objects.get()
    assert admin_api.post(f"{ADMIN}{row.pk}/approve/").status_code == 400
    row.refresh_from_db()
    assert row.status == "verified"


def test_only_provisioners_see_and_decide_sign_ups(enabled):
    anon, user = Api(), Api()
    user.login(make_user("plain@example.com"), expect="authenticated")
    assert anon.get(ADMIN).status_code in (401, 403)
    assert user.get(ADMIN).status_code == 403
    assert user.post(f"{ADMIN}00000000-0000-0000-0000-000000000000/approve/").status_code == 403
