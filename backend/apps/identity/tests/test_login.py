"""Login (plan §6.1, §6.2): enumeration safety, equal work, CSRF, throttling and lockout."""

from unittest import mock

import pytest
from django.contrib.auth.hashers import MD5PasswordHasher
from django.core import mail
from django.core.cache import cache
from freezegun import freeze_time

from apps.audit.models import AuditEvent
from apps.identity.models import SessionRecord
from tests.helpers import PASSWORD, Api, make_user

pytestmark = pytest.mark.django_db

LOGIN = "/api/v1/auth/login/"


WRONG = "Wrong-password-123"


def _attempt(api, email, attempt=WRONG):
    return api.post(LOGIN, {"email": email, "password": attempt})


def test_successful_login_creates_session_record_and_audit(api):
    person = make_user()
    assert api.login(person) == "authenticated"
    record = SessionRecord.objects.get(user=person.user)
    assert record.revoked_at is None and record.ip_prefix == "198.51.100.0/24"
    assert record.user_agent_summary == "Firefox on Linux"
    assert AuditEvent.objects.filter(
        action="identity.login.succeeded", actor_user_id=person.user.pk
    ).exists()
    assert api.get("/api/v1/me/").status_code == 200


def test_login_requires_csrf(api):
    make_user()
    response = api.post(LOGIN, {"email": "person@example.com", "password": PASSWORD}, csrf=False)
    assert response.status_code == 403


def test_failures_are_indistinguishable_and_do_equal_hashing(api):
    make_user("known@example.com")
    make_user("inactive@example.com", active=False)
    make_user("pending@example.com", activated=False, password=None)
    cases = {
        "unknown": ("nobody@example.com", PASSWORD),
        "wrong_password": ("known@example.com", "Wrong-password-123"),
        "inactive": ("inactive@example.com", PASSWORD),
        "unactivated": ("pending@example.com", PASSWORD),
    }
    bodies = {}
    for name, (email, password) in cases.items():
        with mock.patch.object(
            MD5PasswordHasher, "encode", autospec=True, side_effect=MD5PasswordHasher.encode
        ) as enc:
            response = Api().post(LOGIN, {"email": email, "password": password})
        assert response.status_code == 401, name
        assert enc.call_count == 1, f"{name}: password hashed {enc.call_count} times"
        body = response.json()
        body.pop("request_id")
        bodies[name] = body
    assert len({repr(b) for b in bodies.values()}) == 1
    assert bodies["unknown"]["code"] == "invalid_credentials"


def test_failed_login_audit_contains_no_email_or_password(api):
    make_user("known@example.com")
    _attempt(api, "known@example.com", "Sup3r-secret-attempt")
    event = AuditEvent.objects.get(action="identity.login.failed")
    assert event.metadata == {"reason": "invalid_credentials"}
    assert "known@example.com" not in repr(event.__dict__)
    assert "Sup3r-secret-attempt" not in repr(event.__dict__)


def test_per_ip_limit():
    api = Api(remote_addr="203.0.113.50")
    for i in range(20):
        assert _attempt(api, f"user{i}@example.com").status_code == 401
    response = _attempt(api, "another@example.com")
    assert response.status_code == 429
    assert int(response["Retry-After"]) > 0
    assert response.json()["code"] == "rate_limited"
    assert AuditEvent.objects.filter(action="identity.login.throttled").exists()


@pytest.mark.parametrize("email", ["known@example.com", "nobody@example.com"])
def test_per_email_progressive_delay_then_lock_identical_for_unknown(email):
    person = make_user("known@example.com")
    with freeze_time("2026-11-06 10:00:00") as clock:
        for _ in range(2):
            assert _attempt(Api(), email).status_code == 401
        assert _attempt(Api(), email).status_code == 401  # 3rd failure: delay starts
        delayed = _attempt(Api(), email)
        assert delayed.status_code == 429 and delayed.json()["retry_after"] == 2
        clock.tick(3)
        assert _attempt(Api(), email).status_code == 401  # 4th
        clock.tick(5)
        assert _attempt(Api(), email).status_code == 401  # 5th -> lock
        locked = Api().post(LOGIN, {"email": email, "password": PASSWORD})
        assert locked.status_code == 429
        assert 0 < locked.json()["retry_after"] <= 15 * 60
        clock.tick(15 * 60 + 1)
        if email == person.user.email:
            assert Api().login(person) == "authenticated"
    assert AuditEvent.objects.filter(action="identity.login.locked").count() == 1
    notices = [m for m in mail.outbox if "locked" in m.subject.lower()]
    assert len(notices) == (1 if email == person.user.email else 0)


def test_throttle_keys_contain_no_plaintext_ip_or_email():
    api = Api(remote_addr="203.0.113.77")
    _attempt(api, "Someone@Example.com")
    keys = " ".join(str(k) for k in cache._cache)  # type: ignore[attr-defined]  # locmem
    assert keys
    for plaintext in ("203.0.113.77", "someone@example.com", "Someone@Example.com"):
        assert plaintext not in keys


def test_mfa_login_flow_replay_window_and_attempt_limit():
    person = make_user("mfa@example.com", mfa=True)
    api = Api()
    first = api.post(LOGIN, {"email": person.user.email, "password": PASSWORD})
    assert first.json() == {"status": "mfa_required"}
    assert api.get("/api/v1/me/").status_code == 401  # not logged in yet
    # Both codes are taken at ONE instant. Asking the clock again for "the same step" made
    # this test fail whenever the run crossed a 30-second TOTP boundary in between: the
    # second call then returned a fresh, valid code instead of the one already used.
    used, following = person.code(), person.code(1)
    assert api.post("/api/v1/auth/mfa/verify/", {"code": used}).status_code == 200
    assert api.get("/api/v1/me/").json()["session"]["mfa_verified"] is True

    # Replay of the same step in a new login is rejected; the next step (+1) is accepted.
    second = Api()
    second.post(LOGIN, {"email": person.user.email, "password": PASSWORD})
    replay = second.post("/api/v1/auth/mfa/verify/", {"code": used})
    assert replay.status_code == 401 and replay.json()["code"] == "invalid_mfa_code"
    assert second.post("/api/v1/auth/mfa/verify/", {"code": following}).status_code == 200

    third = Api()
    third.post(LOGIN, {"email": person.user.email, "password": PASSWORD})
    for _ in range(4):
        assert third.post("/api/v1/auth/mfa/verify/", {"code": "000000"}).status_code == 401
    final = third.post("/api/v1/auth/mfa/verify/", {"code": "000000"})
    assert final.json()["code"] == "mfa_challenge_expired"
    assert third.post("/api/v1/auth/mfa/verify/", {"code": person.code(1)}).json()["code"] == (
        "mfa_challenge_expired"
    )


def test_mfa_codes_outside_the_window_are_rejected():
    person = make_user("mfa@example.com", mfa=True)
    api = Api()
    api.post(LOGIN, {"email": person.user.email, "password": PASSWORD})
    assert api.post("/api/v1/auth/mfa/verify/", {"code": person.code(-2)}).status_code == 401
    assert api.post("/api/v1/auth/mfa/verify/", {"code": person.code(2)}).status_code == 401
    assert api.post("/api/v1/auth/mfa/verify/", {"code": person.code(-1)}).status_code == 200


def test_pending_mfa_expires_after_five_minutes():
    person = make_user("mfa@example.com", mfa=True)
    with freeze_time("2026-11-06 10:00:00") as clock:
        api = Api()
        api.post(LOGIN, {"email": person.user.email, "password": PASSWORD})
        clock.tick(5 * 60 + 1)
        response = api.post("/api/v1/auth/mfa/verify/", {"code": person.code()})
    assert response.json()["code"] == "mfa_challenge_expired"


def test_login_rotates_the_session_key():
    person = make_user()
    api = Api()
    api.get("/api/v1/auth/csrf/")
    api.client.session.save()
    before = api.client.cookies.get("sessionid")
    api.login(person)
    after = api.client.cookies["sessionid"].value
    assert before is None or before.value != after
