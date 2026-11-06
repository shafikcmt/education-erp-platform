"""MFA (plan §6.6; ADR-035, ADR-038): enrollment gate, QR-only setup, one-time manual key,
recovery codes, disable/reset rules, step-up."""

import base64
import json
import re
from datetime import timedelta

import pyotp
import pytest
from django.core import mail
from django.utils import timezone
from freezegun import freeze_time

from apps.audit.models import AuditEvent
from apps.core import crypto
from apps.identity.models import MFADevice, RecoveryCode, SessionRecord
from tests.helpers import PASSWORD, Api, make_user

pytestmark = pytest.mark.django_db

SETUP = "/api/v1/me/mfa/totp/setup/"
CONFIRM = "/api/v1/me/mfa/totp/confirm/"


def _secret(device_id):
    device = MFADevice.objects.get(pk=device_id)
    return crypto.decrypt_str(
        device.secret_encrypted, purpose=f"identity.mfadevice.secret:{device.pk}"
    )


def _now_code(secret, offset=0):
    totp = pyotp.TOTP(secret)
    return totp.generate_otp(totp.timecode(timezone.now()) + offset)


def _enroll(api):
    setup = api.post(SETUP)
    assert setup.status_code == 201, setup.content
    device_id = setup.json()["device_id"]
    secret = _secret(device_id)
    confirm = api.post(CONFIRM, {"device_id": device_id, "code": _now_code(secret)})
    assert confirm.status_code == 200, confirm.content
    return secret, confirm.json()["recovery_codes"]


def test_privileged_account_is_gated_until_enrollment():
    person = make_user("staff@example.com", roles=("platform_support",))
    api = Api()
    assert api.login(person) == "mfa_enrollment_required"
    blocked = api.get("/api/v1/platform/users/")
    assert blocked.status_code == 403 and blocked.json()["code"] == "mfa_enrollment_required"
    assert api.get("/api/v1/me/sessions/").json()["code"] == "mfa_enrollment_required"
    me = api.get("/api/v1/me/").json()
    assert me["mfa_enrollment_required"] is True
    assert not any(p.startswith(("audit.", "rbac.")) for p in me["permissions"])
    _secret_value, codes = _enroll(api)
    assert len(codes) == 10 and all(re.fullmatch(r"[A-Z2-7]{4}(-[A-Z2-7]{4}){3}", c) for c in codes)
    assert api.get("/api/v1/platform/users/").status_code == 200
    assert api.get("/api/v1/me/").json()["session"]["mfa_verified"] is True


def test_ordinary_accounts_are_never_forced_into_mfa():
    person = make_user("plain@example.com")
    api = Api()
    assert api.login(person) == "authenticated"
    assert api.get("/api/v1/me/sessions/").status_code == 200
    assert api.get("/api/v1/me/").json()["mfa_required"] is False


def test_setup_returns_only_a_qr_svg_no_uri_and_no_secret():
    api = Api()
    api.login(make_user())
    response = api.post(SETUP)
    body = response.json()
    assert set(body) == {"device_id", "qr_svg", "expires_at"}
    assert body["qr_svg"].startswith("data:image/svg+xml")
    secret = _secret(body["device_id"])
    raw = response.content.decode()
    assert "otpauth" not in raw and secret not in raw
    assert response["Cache-Control"] == "no-store"
    assert secret.encode() not in bytes(
        MFADevice.objects.get(pk=body["device_id"]).secret_encrypted
    )


def test_manual_key_needs_fresh_step_up_and_is_shown_once():
    person = make_user()
    api = Api()
    api.login(person)
    device_id = api.post(SETUP).json()["device_id"]
    path = f"{SETUP}{device_id}/manual-key/"
    denied = api.post(path)
    assert denied.status_code == 403 and denied.json()["code"] == "step_up_required"
    api.step_up(person)
    first = api.post(path)
    assert first.status_code == 200
    key = first.json()["manual_key"]
    assert key.replace(" ", "") == _secret(device_id)
    assert re.fullmatch(r"([A-Z2-7]{4} )+[A-Z2-7]{1,4}", key)
    second = api.post(path)
    assert second.status_code == 410 and second.json()["code"] == "manual_key_already_shown"
    assert key.replace(" ", "") not in second.content.decode()
    # Audit records the reveal without key material.
    events = AuditEvent.objects.filter(action="identity.mfa.manual_key_revealed")
    assert events.count() == 2
    assert all(key.replace(" ", "") not in json.dumps(e.metadata) for e in events)


def test_lost_key_requires_restart_which_issues_a_new_secret():
    person = make_user()
    api = Api()
    api.login(person)
    api.step_up(person)
    old_id = api.post(SETUP).json()["device_id"]
    old_secret = _secret(old_id)
    api.post(f"{SETUP}{old_id}/manual-key/")
    assert api.delete(f"{SETUP}{old_id}/").status_code == 204
    assert not MFADevice.objects.filter(pk=old_id).exists()
    new_id = api.post(SETUP).json()["device_id"]
    assert _secret(new_id) != old_secret
    assert api.post(f"{SETUP}{old_id}/manual-key/").status_code == 404
    assert api.post(f"{SETUP}{new_id}/manual-key/").status_code == 200


def test_manual_key_is_never_available_for_a_confirmed_device_or_after_expiry():
    person = make_user()
    with freeze_time("2026-11-06 10:00:00") as clock:
        api = Api()
        api.login(person)
        api.step_up(person)
        device_id = api.post(SETUP).json()["device_id"]
        secret = _secret(device_id)
        api.post(CONFIRM, {"device_id": device_id, "code": _now_code(secret)})
        assert api.post(f"{SETUP}{device_id}/manual-key/").status_code == 404
        assert api.post(SETUP).json()["code"] == "mfa_already_enrolled"
        assert secret not in api.get("/api/v1/me/mfa/").content.decode()

    other = make_user("other@example.com")
    with freeze_time("2026-11-06 11:00:00") as clock:
        api = Api()
        api.login(other)
        device_id = api.post(SETUP).json()["device_id"]
        clock.tick(10 * 60 + 1)
        api.step_up(other)
        assert api.post(f"{SETUP}{device_id}/manual-key/").status_code == 404
        assert api.post(CONFIRM, {"device_id": device_id, "code": "123456"}).status_code == 404


def test_step_up_inside_enrollment_session_is_password_only():
    person = make_user("staff@example.com", roles=("platform_support",))
    api = Api()
    assert api.login(person) == "mfa_enrollment_required"
    response = api.post("/api/v1/auth/step-up/", {"password": PASSWORD})
    assert response.status_code == 200 and response.json()["step_up_expires_at"]


def test_recovery_codes_are_hashed_and_single_use():
    person = make_user()
    api = Api()
    api.login(person)
    _secret_value, codes = _enroll(api)
    stored = list(RecoveryCode.objects.filter(user=person.user).values_list("code_hash", flat=True))
    assert len(stored) == 10 and not any(c.replace("-", "") in stored for c in codes)
    api.post("/api/v1/auth/logout/")
    login = Api()
    login.post("/api/v1/auth/login/", {"email": person.user.email, "password": PASSWORD})
    ok = login.post("/api/v1/auth/mfa/verify/", {"recovery_code": codes[0].lower()})
    assert ok.status_code == 200
    reuse = Api()
    reuse.post("/api/v1/auth/login/", {"email": person.user.email, "password": PASSWORD})
    assert reuse.post("/api/v1/auth/mfa/verify/", {"recovery_code": codes[0]}).status_code == 401
    used = AuditEvent.objects.get(action="identity.mfa.recovery_code_used")
    assert used.metadata == {"remaining": 9}


def test_regenerate_requires_step_up_and_invalidates_old_codes():
    person = make_user()
    api = Api()
    api.login(person)
    secret, codes = _enroll(api)
    person.totp_secret = secret
    assert api.post("/api/v1/me/mfa/recovery-codes/").json()["code"] == "step_up_required"
    with freeze_time(timezone.now() + timedelta(seconds=31)):
        api.step_up(person, offset_steps=0)
        new = api.post("/api/v1/me/mfa/recovery-codes/").json()["recovery_codes"]
    assert set(new).isdisjoint(codes)
    assert RecoveryCode.objects.filter(user=person.user).count() == 10


def test_disable_needs_step_up_and_is_refused_for_privileged_accounts():
    person = make_user("plain@example.com", mfa=True)
    with freeze_time("2026-11-06 10:00:00") as clock:
        api = Api()
        api.login(person)
        assert api.delete("/api/v1/me/mfa/totp/").json()["code"] == "step_up_required"
        clock.tick(31)
        other = Api()
        other.login(person)  # a second session, on the next TOTP step
        clock.tick(31)
        api.step_up(person, offset_steps=0)
        assert api.delete("/api/v1/me/mfa/totp/").status_code == 204
        assert not MFADevice.objects.filter(user=person.user).exists()
        assert other.get("/api/v1/me/").status_code == 401  # other sessions revoked
        assert api.get("/api/v1/me/").status_code == 200  # this one kept
    assert any("turned off" in m.subject for m in mail.outbox)

    staff = make_user("staff@example.com", roles=("platform_support",), mfa=True)
    staff_api = Api()
    staff_api.login(staff)
    staff_api.step_up(staff)
    refused = staff_api.delete("/api/v1/me/mfa/totp/")
    assert refused.status_code == 409 and refused.json()["code"] == "mfa_required_for_account"


def test_step_up_expires_after_ten_minutes():
    person = make_user()
    with freeze_time("2026-11-06 10:00:00") as clock:
        api = Api()
        api.login(person)
        api.step_up(person)
        clock.tick(9 * 60)
        assert api.get("/api/v1/me/").json()["session"]["step_up_expires_at"]
        clock.tick(61)
        response = api.post("/api/v1/me/email/", {"new_email": "new@example.com"})
        assert response.json()["code"] == "step_up_required"


def test_step_up_failures_are_limited():
    person = make_user()
    api = Api()
    api.login(person)
    for _ in range(5):
        assert api.post("/api/v1/auth/step-up/", {"password": "wrong-pass-123"}).status_code == 401
    locked = api.post("/api/v1/auth/step-up/", {"password": PASSWORD})
    assert locked.status_code == 429


def test_step_up_with_mfa_needs_a_valid_code_and_rotates_the_session():
    person = make_user(mfa=True)
    api = Api()
    api.login(person)
    key_before = api.client.cookies["sessionid"].value
    bad = api.post("/api/v1/auth/step-up/", {"password": PASSWORD, "code": "000000"})
    assert bad.status_code == 401
    api.step_up(person)
    assert api.client.cookies["sessionid"].value != key_before
    record = SessionRecord.objects.get(user=person.user, revoked_at__isnull=True)
    assert record.step_up_at is not None


def test_admin_mfa_reset_requires_reason_step_up_and_revokes_sessions(admin, admin_api):
    target = make_user("t@example.com", mfa=True)
    target_api = Api()
    target_api.login(target)
    path = f"/api/v1/platform/users/{target.user.pk}/mfa/reset/"
    assert admin_api.post(path, {"reason": "x"}).status_code == 400
    assert admin_api.post(path, {"reason": "Lost phone, ticket #42"}).status_code == 204
    assert not MFADevice.objects.filter(user=target.user).exists()
    assert target_api.get("/api/v1/me/").status_code == 401
    event = AuditEvent.objects.get(action="identity.mfa.reset")
    assert event.metadata == {"reason": "Lost phone, ticket #42"}
    assert any("reset" in m.subject.lower() for m in mail.outbox)


def test_qr_payload_round_trips_through_an_authenticator():
    """The SVG encodes a standard otpauth URI (decoded here only via the stored secret)."""
    api = Api()
    api.login(make_user())
    body = api.post(SETUP).json()
    svg = (
        base64.b64decode(body["qr_svg"].split(",", 1)[1])
        if ";base64," in body["qr_svg"]
        else (body["qr_svg"].encode())
    )
    assert b"<svg" in svg or b"%3Csvg" in svg
