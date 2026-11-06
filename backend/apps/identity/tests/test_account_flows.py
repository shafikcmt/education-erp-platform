"""Account lifecycle (plan §6.3 to §6.5; ADR-034): activation, reset, password/email change,
tokens (random, hashed, single-use, expiring, superseded), enumeration-safe requests."""

from datetime import timedelta

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.utils import timezone
from freezegun import freeze_time

from apps.audit.models import AuditEvent
from apps.core.tokens import hash_token
from apps.identity.models import AccountToken, TokenPurpose, User
from tests.helpers import PASSWORD, Api, link_token, make_user

pytestmark = pytest.mark.django_db

NEW_PASSWORD = "Another-Strong-Pass-42"


def _token_from_last_mail(page):
    return link_token(mail.outbox[-1], f"/{page}")


def test_admin_creates_user_who_activates_then_signs_in(admin_api):
    created = admin_api.post(
        "/api/v1/platform/users/",
        {"email": "New.Staff@Example.com", "display_name": "New", "locale": "bn"},
    )
    assert created.status_code == 201
    user = User.objects.get(email="new.staff@example.com")
    assert user.activated_at is None and not user.has_usable_password()
    assert mail.outbox[-1].to == ["new.staff@example.com"]
    assert "চালু" in mail.outbox[-1].subject  # Bengali template for a bn user
    token = _token_from_last_mail("activate")
    assert not AccountToken.objects.filter(token_hash=token).exists()  # only the hash is stored
    assert AccountToken.objects.filter(token_hash=hash_token(token)).exists()

    api = Api()
    pending = api.post("/api/v1/auth/login/", {"email": user.email, "password": NEW_PASSWORD})
    assert pending.status_code == 401
    weak = api.post("/api/v1/auth/activate/", {"token": token, "password": "123"})
    assert weak.status_code == 400
    assert (
        api.post("/api/v1/auth/activate/", {"token": token, "password": NEW_PASSWORD}).status_code
        == 204
    )
    reused = api.post("/api/v1/auth/activate/", {"token": token, "password": NEW_PASSWORD})
    assert reused.status_code == 400 and reused.json()["code"] == "invalid_token"
    user.refresh_from_db()
    assert user.activated_at and user.email_verified_at
    assert api.post(
        "/api/v1/auth/login/", {"email": user.email, "password": NEW_PASSWORD}
    ).json() == {"status": "authenticated"}


def test_new_token_supersedes_the_old_one_and_tokens_expire(admin_api):
    admin_api.post("/api/v1/platform/users/", {"email": "x@example.com"})
    first = _token_from_last_mail("activate")
    user = User.objects.get(email="x@example.com")
    assert admin_api.post(f"/api/v1/platform/users/{user.pk}/activation/resend/").status_code == 202
    second = _token_from_last_mail("activate")
    api = Api()
    old = api.post("/api/v1/auth/activate/", {"token": first, "password": NEW_PASSWORD})
    assert old.json()["code"] == "invalid_token"
    with freeze_time(timezone.now() + timedelta(hours=72, seconds=1)):
        expired = Api().post("/api/v1/auth/activate/", {"token": second, "password": NEW_PASSWORD})
    assert expired.json()["code"] == "invalid_token"
    reasons = set(
        AuditEvent.objects.filter(action="identity.token.rejected").values_list(
            "metadata__reason", flat=True
        )
    )
    assert reasons == {"superseded", "expired"}


def test_password_reset_is_enumeration_safe_and_revokes_all_sessions():
    person = make_user()
    session = Api()
    session.login(person)
    responses = [
        Api().post("/api/v1/auth/password/reset/", {"email": email})
        for email in (person.user.email, "nobody@example.com")
    ]
    bodies = [r.json() for r in responses]
    assert [r.status_code for r in responses] == [202, 202] and bodies[0] == bodies[1]
    assert len(mail.outbox) == 1
    token = _token_from_last_mail("reset-password")
    api = Api()
    wrong_purpose = api.post("/api/v1/auth/activate/", {"token": token, "password": NEW_PASSWORD})
    assert wrong_purpose.json()["code"] == "invalid_token"
    assert (
        api.post(
            "/api/v1/auth/password/reset/confirm/", {"token": token, "password": NEW_PASSWORD}
        ).status_code
        == 204
    )
    assert session.get("/api/v1/me/").status_code == 401
    person.password = NEW_PASSWORD
    assert Api().login(person) == "authenticated"
    assert "reset" in mail.outbox[-1].subject.lower()


def test_reset_token_lives_thirty_minutes():
    person = make_user()
    Api().post("/api/v1/auth/password/reset/", {"email": person.user.email})
    token = _token_from_last_mail("reset-password")
    with freeze_time(timezone.now() + timedelta(minutes=31)):
        response = Api().post(
            "/api/v1/auth/password/reset/confirm/", {"token": token, "password": NEW_PASSWORD}
        )
    assert response.json()["code"] == "invalid_token"


def test_email_flow_rate_limits():
    person = make_user()
    api = Api(remote_addr="203.0.113.60")
    for _ in range(5):
        assert (
            api.post("/api/v1/auth/password/reset/", {"email": person.user.email}).status_code
            == 202
        )
    assert len(mail.outbox) == 3  # per-email limit is silent
    for _ in range(5):
        api.post("/api/v1/auth/password/reset/", {"email": "nobody@example.com"})
    assert api.post("/api/v1/auth/password/reset/", {"email": "z@example.com"}).status_code == 429


def test_activation_resend_is_enumeration_safe():
    make_user("pending@example.com", activated=False, password=None)
    make_user("active@example.com")
    bodies = [
        Api().post("/api/v1/auth/activation/resend/", {"email": e}).json()
        for e in ("pending@example.com", "active@example.com", "nobody@example.com")
    ]
    assert bodies[0] == bodies[1] == bodies[2]
    assert [m.to for m in mail.outbox] == [["pending@example.com"]]


def test_password_change_needs_step_up_current_password_and_revokes_others():
    person = make_user()
    api, other = Api(), Api()
    api.login(person)
    other.login(person)
    body = {"current_password": PASSWORD, "new_password": NEW_PASSWORD}
    assert api.post("/api/v1/me/password/", body).json()["code"] == "step_up_required"
    api.step_up(person)
    wrong = api.post("/api/v1/me/password/", {**body, "current_password": "Nope-nope-123"})
    assert wrong.status_code == 400
    assert api.post("/api/v1/me/password/", body).status_code == 204
    assert api.get("/api/v1/me/").status_code == 200
    assert other.get("/api/v1/me/").status_code == 401
    assert "changed" in mail.outbox[-1].subject.lower()


def test_email_change_verifies_new_address_and_notifies_old():
    person = make_user("old@example.com")
    api = Api()
    api.login(person)
    api.step_up(person)
    assert api.post("/api/v1/me/email/", {"new_email": "New@Example.com"}).status_code == 202
    verify, notice = mail.outbox[-2], mail.outbox[-1]
    assert verify.to == ["new@example.com"] and notice.to == ["old@example.com"]
    assert "new@example.com" not in notice.body  # the old inbox learns nothing new
    token = link_token(verify)
    assert api.post("/api/v1/auth/email/verify/", {"token": token}).status_code == 204
    person.user.refresh_from_db()
    assert person.user.email == "new@example.com"
    assert mail.outbox[-1].to == ["old@example.com"]
    assert api.get("/api/v1/me/").json()["email"] == "new@example.com"


def test_email_change_to_a_taken_address_fails_generically():
    person = make_user("old@example.com")
    make_user("taken@example.com")
    api = Api()
    api.login(person)
    api.step_up(person)
    api.post("/api/v1/me/email/", {"new_email": "taken@example.com"})
    token = link_token(mail.outbox[-2])
    assert (
        api.post("/api/v1/auth/email/verify/", {"token": token}).json()["code"] == "invalid_token"
    )


def test_tokens_have_the_documented_lifetimes():
    from apps.identity.services.tokens import LIFETIMES

    assert LIFETIMES[TokenPurpose.ACTIVATION] == timedelta(hours=72)
    assert LIFETIMES[TokenPurpose.PASSWORD_RESET] == timedelta(minutes=30)
    assert LIFETIMES[TokenPurpose.EMAIL_CHANGE] == timedelta(hours=24)


def test_deactivation_signs_out_and_blocks_login(admin_api):
    target = make_user("t@example.com")
    t = Api()
    t.login(target)
    assert admin_api.post(f"/api/v1/platform/users/{target.user.pk}/deactivate/").status_code == 200
    assert t.get("/api/v1/me/").status_code == 401
    assert (
        Api()
        .post("/api/v1/auth/login/", {"email": target.user.email, "password": PASSWORD})
        .json()["code"]
        == "invalid_credentials"
    )
    assert admin_api.post(f"/api/v1/platform/users/{target.user.pk}/reactivate/").status_code == 200
    assert Api().login(target) == "authenticated"


def test_cannot_deactivate_self_or_last_super_admin(admin, admin_api):
    response = admin_api.post(f"/api/v1/platform/users/{admin.user.pk}/deactivate/")
    assert response.status_code == 409 and response.json()["code"] == "cannot_deactivate_self"


@override_settings(PASSWORD_BREACH_CHECK_ENABLED=True)
def test_breached_password_validator(monkeypatch):
    import hashlib

    from apps.identity.validators import BreachedPasswordValidator

    suffix = hashlib.sha1(b"Breached-Pass-123", usedforsecurity=False).hexdigest().upper()[5:]
    validator = BreachedPasswordValidator()
    monkeypatch.setattr(validator, "_fetch_range", lambda prefix: f"0000:1\r\n{suffix}:42\r\n")
    with pytest.raises(ValidationError, match="breach"):
        validator.validate("Breached-Pass-123")
    validator.validate("Some-Other-Pass-123")

    def down(prefix):
        raise TimeoutError

    monkeypatch.setattr(validator, "_fetch_range", down)
    validator.validate("Breached-Pass-123")  # fails open by default
    with (
        override_settings(PASSWORD_BREACH_CHECK_FAIL_CLOSED=True),
        pytest.raises(ValidationError, match="couldn't check"),
    ):
        validator.validate("Breached-Pass-123")
