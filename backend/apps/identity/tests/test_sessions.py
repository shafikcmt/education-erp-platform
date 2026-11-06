"""Sessions (plan §6.7): idle/absolute timeouts, listing with masked IPs, revocation."""

import pytest
from freezegun import freeze_time

from apps.audit.models import AuditEvent
from apps.identity.models import SessionRecord
from tests.helpers import Api, make_user

pytestmark = pytest.mark.django_db


def test_idle_timeout_is_thirty_minutes():
    person = make_user()
    with freeze_time("2026-11-06 10:00:00") as clock:
        api = Api()
        api.login(person)
        clock.tick(29 * 60)
        assert api.get("/api/v1/me/").status_code == 200  # activity refreshes the timer
        clock.tick(29 * 60)
        assert api.get("/api/v1/me/").status_code == 200
        clock.tick(30 * 60 + 1)
        assert api.get("/api/v1/me/").status_code == 401
    assert AuditEvent.objects.filter(action="identity.session.expired_idle").exists()
    assert SessionRecord.objects.get(user=person.user).revoke_reason == "expired_idle"


def test_absolute_lifetime_is_twelve_hours_despite_activity():
    person = make_user()
    with freeze_time("2026-11-06 08:00:00") as clock:
        api = Api()
        api.login(person)
        for _ in range(24):
            clock.tick(29 * 60)
            assert api.get("/api/v1/me/").status_code == 200
        clock.tick(25 * 60)  # 24 x 29 min + 25 min = 12 h 1 min since login
        assert api.get("/api/v1/me/").status_code == 401
    assert AuditEvent.objects.filter(action="identity.session.expired_absolute").exists()


def test_me_reports_expiry_times_for_the_idle_warning():
    person = make_user()
    with freeze_time("2026-11-06 10:00:00"):
        api = Api()
        api.login(person)
        session = api.get("/api/v1/me/").json()["session"]
    assert session["idle_timeout_seconds"] == 1800
    assert session["absolute_expires_at"] - session["idle_expires_at"] == 12 * 3600 - 1800


def test_list_and_revoke_own_sessions_with_masked_ips():
    person = make_user()
    first, second = Api(remote_addr="203.0.113.9"), Api(remote_addr="198.51.100.20")
    first.login(person)
    second.login(person)
    listed = first.get("/api/v1/me/sessions/").json()
    assert len(listed) == 2
    assert {s["ip_masked"] for s in listed} == {"203.0.113.•", "198.51.100.•"}
    assert "203.0.113.9" not in repr(listed)
    current = [s for s in listed if s["current"]]
    assert len(current) == 1 and current[0]["ip_masked"] == "203.0.113.•"
    other_id = next(s["id"] for s in listed if not s["current"])
    assert first.delete(f"/api/v1/me/sessions/{other_id}/").status_code == 204
    assert second.get("/api/v1/me/").status_code == 401
    assert first.get("/api/v1/me/").status_code == 200
    assert first.delete("/api/v1/me/sessions/not-a-uuid/").status_code == 404


def test_cannot_revoke_someone_elses_session():
    alice, bob = make_user("alice@example.com"), make_user("bob@example.com")
    a, b = Api(), Api()
    a.login(alice)
    b.login(bob)
    bob_record = SessionRecord.objects.get(user=bob.user)
    assert a.delete(f"/api/v1/me/sessions/{bob_record.pk}/").status_code == 404
    assert b.get("/api/v1/me/").status_code == 200


def test_revoke_others_and_revoking_current_logs_out():
    person = make_user()
    clients = [Api(), Api(), Api()]
    for c in clients:
        c.login(person)
    assert clients[0].post("/api/v1/me/sessions/revoke-others/").json() == {"revoked": 2}
    assert [c.get("/api/v1/me/").status_code for c in clients] == [200, 401, 401]
    me = SessionRecord.objects.get(user=person.user, revoked_at__isnull=True)
    assert clients[0].delete(f"/api/v1/me/sessions/{me.pk}/").status_code == 204
    assert clients[0].get("/api/v1/me/").status_code == 401


def test_logout_revokes_the_record():
    person = make_user()
    api = Api()
    api.login(person)
    assert api.post("/api/v1/auth/logout/").status_code == 204
    assert api.get("/api/v1/me/").status_code == 401
    assert SessionRecord.objects.get(user=person.user).revoke_reason == "logout"


def test_admin_revoke_any_needs_permission_and_step_up(admin, admin_api):
    target = make_user("t@example.com")
    t = Api()
    t.login(target)
    path = f"/api/v1/platform/users/{target.user.pk}/sessions/revoke/"
    assert t.post(path).status_code == 403  # no permission
    assert admin_api.post(path).json() == {"revoked": 1}
    assert t.get("/api/v1/me/").status_code == 401
    second_admin = make_user("admin2@example.com", roles=("super_admin",), mfa=True)
    fresh = Api()
    fresh.login(second_admin)
    assert fresh.post(path).json()["code"] == "step_up_required"


def test_session_key_is_never_stored_in_plaintext():
    person = make_user()
    api = Api()
    api.login(person)
    key = api.client.cookies["sessionid"].value
    record = SessionRecord.objects.get(user=person.user)
    assert key not in repr(record.__dict__)
    assert key.encode() not in bytes(record.session_key_encrypted or b"")
