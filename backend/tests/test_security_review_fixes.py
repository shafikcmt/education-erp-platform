"""Regression tests for the 2026-11-06 security review of PR #15 (H1-H3, M1, M2, M4, L1-L6, I1).

Each test first reproduces the original attack path, then asserts the fix blocks it.
"""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg
import pytest
from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.db import connection, transaction
from django.db.utils import ProgrammingError
from django.test import RequestFactory
from django.utils import timezone
from freezegun import freeze_time

from apps.audit.models import AuditEvent, AuditEventIP
from apps.audit.services import record, reveal_ip
from apps.identity.models import SeenDevice, SessionRecord
from apps.identity.services import sessions
from apps.identity.services.maintenance import run_housekeeping
from apps.rbac import engine
from apps.rbac.models import Permission, PlatformRoleAssignment, Role, RolePermission
from apps.rbac.services import GuardRailViolation
from tests.helpers import PASSWORD, Api, link_token, make_user

pytestmark = pytest.mark.django_db
WRONG_PASSWORD = PASSWORD[::-1]  # synthetic: always differs from the real test password
LOGIN, VERIFY, STEP_UP = "/api/v1/auth/login/", "/api/v1/auth/mfa/verify/", "/api/v1/auth/step-up/"


def _start_mfa_login(person, ip):
    api = Api(remote_addr=ip)
    body = api.post(LOGIN, {"email": person.user.email, "password": PASSWORD}).json()
    assert body == {"status": "mfa_required"}
    return api


# ------------------------------------------------------------------ H1 MFA brute force
def test_h1_mfa_failures_are_counted_per_account_across_relogins_and_lock():
    victim = make_user("v@example.com", mfa=True)
    failures = 0
    for cycle in range(3):  # attacker rotates IPs and re-logs in with the known password
        api = _start_mfa_login(victim, f"203.0.113.{cycle}")
        for _ in range(4):
            response = api.post(VERIFY, {"code": "000000"})
            failures += 1
            if failures == 10:
                assert response.status_code == 429 and response.json()["code"] == "mfa_locked"
                break
            assert response.status_code == 401
        if failures == 10:
            break
    # A fresh password login does not reset the account lock, and even the right code fails.
    api = _start_mfa_login(victim, "198.51.100.200")
    blocked = api.post(VERIFY, {"code": victim.code()})
    assert blocked.status_code == 429 and blocked.json()["code"] == "mfa_locked"
    assert AuditEvent.objects.filter(action="identity.mfa.locked").count() == 1
    assert len([m for m in mail.outbox if "locked" in m.subject.lower()]) == 1


def test_h1_lock_expires_and_admin_reset_clears_it(admin_api):
    victim = make_user("v@example.com", mfa=True)
    with freeze_time("2026-11-06 10:00:00") as clock:
        for _ in range(2):
            api = _start_mfa_login(victim, "203.0.113.9")
            for _ in range(5):
                api.post(VERIFY, {"code": "000000"})
        assert (
            _start_mfa_login(victim, "203.0.113.9")
            .post(VERIFY, {"code": victim.code()})
            .status_code
            == 429
        )
        clock.tick(15 * 60 + 1)
        assert (
            _start_mfa_login(victim, "203.0.113.9")
            .post(VERIFY, {"code": victim.code()})
            .status_code
            == 200
        )


def test_h1_step_up_shares_the_account_mfa_limit():
    person = make_user("p@example.com", mfa=True)
    api = Api()
    api.login(person)
    for i in range(10):
        response = api.post(STEP_UP, {"password": PASSWORD, "code": "000000"})
        assert response.status_code == (429 if i == 9 else 401)
    # Locked for login too.
    assert (
        _start_mfa_login(person, "198.51.100.9")
        .post(VERIFY, {"code": person.code(1)})
        .json()["code"]
        == "mfa_locked"
    )


def test_h1_lock_notice_is_sent_at_most_once_a_day():
    person = make_user("p@example.com", mfa=True)
    with freeze_time("2026-11-06 10:00:00") as clock:
        for _ in range(2):  # two full lock cycles within a day
            for _ in range(10):
                api = _start_mfa_login(person, "203.0.113.5")
                api.post(VERIFY, {"code": "000000"})
            clock.tick(15 * 60 + 1)
    assert AuditEvent.objects.filter(action="identity.mfa.locked").count() == 2
    assert len([m for m in mail.outbox if "locked" in m.subject.lower()]) == 1


# ------------------------------------------------------------------ H2 privileged targets
def _custom_role_user(email, codes):
    person = make_user(email, mfa=True)
    role = Role.objects.create(code=f"r_{uuid.uuid4().hex[:6]}", name="Custom", kind="platform")
    for code in codes:
        RolePermission.objects.create(role=role, permission=Permission.objects.get(code=code))
    PlatformRoleAssignment.objects.create(user=person.user, role=role, granted_at=timezone.now())
    return person


@pytest.fixture
def two_super_admins(db):
    return (
        make_user("sa1@example.com", roles=("super_admin",), mfa=True),
        make_user("sa2@example.com", roles=("super_admin",), mfa=True),
    )


@pytest.mark.parametrize(
    ("path", "body"),
    [("mfa/reset/", {"reason": "social engineering"}), ("sessions/revoke/", None)],
)
def test_h2_support_cannot_act_on_a_super_admin_but_can_on_ordinary_users(
    two_super_admins, path, body
):
    support = make_user("sup@example.com", roles=("platform_support",), mfa=True)
    ordinary = make_user("o@example.com", mfa=True)
    api = Api()
    api.login(support)
    api.step_up(support)
    sa = two_super_admins[0]
    refused = api.post(f"/api/v1/platform/users/{sa.user.pk}/{path}", body)
    assert refused.status_code == 403 and refused.json()["code"] == "insufficient_privilege"
    assert api.post(f"/api/v1/platform/users/{ordinary.user.pk}/{path}", body).status_code < 300


def test_h2_custom_role_cannot_deactivate_or_reactivate_a_super_admin(two_super_admins):
    helpdesk = _custom_role_user(
        "hd@example.com", ["identity.user.deactivate", "identity.user.view"]
    )
    api = Api()
    api.login(helpdesk)
    api.step_up(helpdesk)
    sa = two_super_admins[0]
    assert api.post(f"/api/v1/platform/users/{sa.user.pk}/deactivate/").json()["code"] == (
        "insufficient_privilege"
    )
    sa.user.is_active = False  # a deactivated Super Admin still counts as one
    sa.user.save()
    assert api.post(f"/api/v1/platform/users/{sa.user.pk}/reactivate/").json()["code"] == (
        "insufficient_privilege"
    )


def test_h2_actor_must_hold_every_permission_of_the_target():
    target = make_user("t@example.com", roles=("platform_onboarding",), mfa=True)
    actor = _custom_role_user(
        "a@example.com", ["identity.session.revoke_any", "identity.user.view"]
    )
    with pytest.raises(GuardRailViolation, match="more privileges"):
        sessions.admin_revoke_sessions(actor.user, target.user, request=RequestFactory().get("/"))


def test_h2_super_admin_may_act_on_another_super_admin(two_super_admins, admin_api):
    sa = two_super_admins[0]
    assert (
        admin_api.post(f"/api/v1/platform/users/{sa.user.pk}/sessions/revoke/").status_code == 200
    )


def test_h2_and_l2_services_enforce_permissions_without_the_view():
    plain = make_user("plain@example.com")
    target = make_user("t@example.com")
    request = RequestFactory().get("/")
    with pytest.raises(PermissionDenied):
        sessions.admin_revoke_sessions(plain.user, target.user, request=request)
    from apps.identity.services import accounts, mfa

    with pytest.raises(PermissionDenied):
        mfa.admin_reset_mfa(plain.user, target.user, reason="x" * 10, request=request)
    with pytest.raises(PermissionDenied):
        accounts.reactivate(actor=plain.user, user=target.user, request=request)
    event = record("identity.logout", request=RequestFactory().get("/", REMOTE_ADDR="203.0.113.1"))
    with pytest.raises(PermissionDenied):
        reveal_ip(event, actor=plain.user, request=request)
    assert not AuditEvent.objects.filter(action="audit.ip.revealed").exists()


# ------------------------------------------------------------------ M1 lockout DoS
def test_m1_attackers_on_other_networks_cannot_lock_the_user_out():
    victim = make_user("v@example.com")
    with freeze_time("2026-11-06 10:00:00") as clock:
        for i in range(5):
            Api(remote_addr=f"198.51.100.{i}").post(
                LOGIN, {"email": victim.user.email, "password": WRONG_PASSWORD}
            )
            clock.tick(31)  # attacker respects the global delay
        clock.tick(31)
        ok = Api(remote_addr="192.0.2.50").post(
            LOGIN, {"email": victim.user.email, "password": PASSWORD}
        )
        assert ok.status_code == 200
        # The attacker's own network is locked for this email.
        locked = Api(remote_addr="198.51.100.77").post(
            LOGIN, {"email": victim.user.email, "password": PASSWORD}
        )
    assert locked.status_code == 429


def test_m1_global_delay_is_capped():
    victim = make_user("v@example.com")
    with freeze_time("2026-11-06 10:00:00") as clock:
        delays = []
        for i in range(12):
            r = Api(remote_addr=f"10.{i}.0.1").post(
                LOGIN, {"email": victim.user.email, "password": WRONG_PASSWORD}
            )
            if r.status_code == 429:
                delays.append(r.json()["retry_after"])
            clock.tick(31)
    assert all(d <= settings.SECURITY_LOGIN_MAX_DELAY_SECONDS for d in delays)


def test_m1_lock_notice_once_per_day():
    victim = make_user("v@example.com")
    with freeze_time("2026-11-06 10:00:00") as clock:
        for _cycle in range(3):
            for _ in range(5):
                Api(remote_addr="198.51.100.4").post(
                    LOGIN, {"email": victim.user.email, "password": WRONG_PASSWORD}
                )
                clock.tick(31)
            clock.tick(15 * 60)
    assert AuditEvent.objects.filter(action="identity.login.locked").count() == 3
    assert len([m for m in mail.outbox if "locked" in m.subject.lower()]) == 1


# ------------------------------------------------------------------ M2 token invalidation
def _reset_link(email):
    Api(remote_addr="203.0.113.250").post("/api/v1/auth/password/reset/", {"email": email})
    return link_token(mail.outbox[-1])


def _reset_works(token):
    return (
        Api()
        .post(
            "/api/v1/auth/password/reset/confirm/", {"token": token, "password": "Attacker-Pass-99"}
        )
        .status_code
        == 204
    )


def test_m2_password_change_invalidates_old_reset_links():
    person = make_user("p@example.com")
    stale = _reset_link(person.user.email)
    api = Api()
    api.login(person)
    api.step_up(person)
    api.post(
        "/api/v1/me/password/", {"current_password": PASSWORD, "new_password": "Brand-New-Pass-77"}
    )
    assert not _reset_works(stale)


def test_m2_email_change_invalidates_links_sent_to_the_old_address():
    person = make_user("old@example.com")
    stale = _reset_link("old@example.com")
    api = Api()
    api.login(person)
    api.step_up(person)
    api.post("/api/v1/me/email/", {"new_email": "new@example.com"})
    verify = next(m for m in mail.outbox if m.to == ["new@example.com"])
    assert api.post("/api/v1/auth/email/verify/", {"token": link_token(verify)}).status_code == 204
    assert not _reset_works(stale)


def test_m2_password_reset_invalidates_tokens_of_other_purposes():
    person = make_user("p@example.com")
    api = Api()
    api.login(person)
    api.step_up(person)
    api.post("/api/v1/me/email/", {"new_email": "new@example.com"})
    email_change = link_token(next(m for m in mail.outbox if m.to == ["new@example.com"]))
    assert _reset_works(_reset_link(person.user.email))
    verify = Api().post("/api/v1/auth/email/verify/", {"token": email_change})
    assert verify.status_code == 400 and verify.json()["code"] == "invalid_token"


@pytest.mark.parametrize("action", ["mfa/reset/", "deactivate/"])
def test_m2_admin_actions_invalidate_outstanding_links(admin_api, action):
    person = make_user("p@example.com", mfa=True)
    stale = _reset_link(person.user.email)
    body = {"reason": "lost phone ticket 9"} if action == "mfa/reset/" else None
    assert (
        admin_api.post(f"/api/v1/platform/users/{person.user.pk}/{action}", body).status_code < 300
    )
    assert not _reset_works(stale)
    assert AuditEvent.objects.filter(action="identity.token.invalidated").exists()


# ------------------------------------------------------------------ M4 + L1 housekeeping
def test_m4_device_fingerprints_expire_after_90_days_and_are_erased():
    person = make_user()
    with freeze_time("2026-11-06 10:00:00"):
        Api(remote_addr="203.0.113.44").login(person)
    with freeze_time("2027-02-03 10:00:00"):  # 89 days
        assert run_housekeeping()["seen_devices_purged"] == 0
    with freeze_time("2027-02-05 10:00:00"):  # 91 days
        assert run_housekeeping()["seen_devices_purged"] == 1
    other = make_user("o@example.com")
    Api(remote_addr="203.0.113.45").login(other)
    call_command("erase_ip_data", "--user", str(other.user.pk))
    assert not SeenDevice.objects.filter(user=other.user).exists()


def test_l1_expired_sessions_are_closed_and_keys_dropped():
    person = make_user()
    with freeze_time("2026-11-06 08:00:00"):
        Api().login(person)
    with freeze_time("2026-11-06 19:59:00"):
        assert run_housekeeping()["sessions_closed"] == 0
    with freeze_time("2026-11-06 20:01:00"):
        assert run_housekeeping()["sessions_closed"] == 1
    record_row = SessionRecord.objects.get(user=person.user)
    assert record_row.revoked_at is not None and record_row.session_key_encrypted is None
    assert record_row.revoke_reason == "expired_absolute"


# ------------------------------------------------------------------ L3 cache version token
def test_l3_cache_version_is_random_and_eviction_cannot_reuse_stale_entries():
    user = make_user("u@example.com").user
    first = engine.cache_version()
    assert len(first) == 32 and first != "1"
    engine.effective_permissions(user)  # cached under `first`
    role = Role.objects.get(code="platform_support", tenant_id__isnull=True)
    PlatformRoleAssignment.objects.create(user=user, role=role, granted_at=timezone.now())
    cache.delete("perm:version")  # simulate Redis evicting the version key
    assert engine.cache_version() not in (first, "1")
    assert engine.has_perm(user, "identity.user.view")


# ------------------------------------------------------------------ L4 IP side-table integrity
def _sql(sql, params=()):
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(sql, params)


def test_l4_runtime_role_can_clear_but_not_rewrite_ip_evidence():
    event = record("identity.logout", request=RequestFactory().get("/", REMOTE_ADDR="203.0.113.7"))
    for sql in (
        "UPDATE audit_auditeventip SET ip_encrypted = '\\x00' WHERE event_id = %s",
        "UPDATE audit_auditeventip SET ip_index = 'forged' WHERE event_id = %s",
        "UPDATE audit_auditeventip SET ip_prefix = '192.0.2.0/24' WHERE event_id = %s",
        "UPDATE audit_auditeventip SET created_at = now() - interval '9 years' WHERE event_id = %s",
    ):
        with pytest.raises(ProgrammingError, match="cleared, not rewritten"):
            _sql(sql, [event.pk])
    _sql(
        "UPDATE audit_auditeventip SET ip_encrypted = NULL, ip_index = NULL, anonymized_at = now()"
        " WHERE event_id = %s",
        [event.pk],
    )
    assert AuditEventIP.objects.get(event=event).ip_encrypted is None


def test_l4_runtime_role_cannot_insert_ip_rows_for_existing_events():
    old = AuditEvent.objects.create(
        occurred_at=timezone.now(), actor_type="system", action="identity.logout", outcome="success"
    )
    # Same transaction as the event (the test transaction): allowed, as record() does.
    AuditEventIP.objects.create(event=old, ip_prefix="203.0.113.0/24", created_at=timezone.now())
    # An event written in an EARLIER transaction can't receive (forged) IP rows.
    with psycopg.connect(**_app_dsn()) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO audit_auditevent (id, occurred_at, actor_type, action, outcome, "
            "target_type, target_id, metadata, user_agent_summary, request_id) VALUES "
            "(%s, now(), 'system', 'identity.logout', 'success', '', '', '{}', '', '')",
            [eid := uuid.uuid4()],
        )
        conn.commit()
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="only be added"):
            cur.execute(
                "INSERT INTO audit_auditeventip (event_id, ip_prefix, created_at) "
                "VALUES (%s, '198.51.100.0/24', now())",
                [eid],
            )


def _app_dsn():
    db = connection.settings_dict
    return {
        "dbname": db["NAME"],
        "host": db["HOST"] or "localhost",
        "port": db["PORT"] or 5432,
        "user": settings.TEST_APP_DB_USER,
        "password": settings.TEST_APP_DB_PASSWORD,
    }


def test_l4_owner_role_may_rewrite_for_key_rotation(owner_dsn):
    with psycopg.connect(**owner_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO audit_auditevent (id, occurred_at, actor_type, action, outcome, "
            "target_type, target_id, metadata, user_agent_summary, request_id) VALUES "
            "(%s, now(), 'system', 'identity.logout', 'success', '', '', '{}', '', '')",
            [eid := uuid.uuid4()],
        )
        cur.execute(
            "INSERT INTO audit_auditeventip (event_id, ip_encrypted, ip_index, ip_prefix, "
            "created_at) VALUES (%s, '\\x01', 'a', '203.0.113.0/24', now())",
            [eid],
        )
        cur.execute(
            "UPDATE audit_auditeventip SET ip_encrypted = '\\x02', ip_index = 'b' "
            "WHERE event_id = %s",
            [eid],
        )
        cur.execute("SELECT recorded_tx_at IS NOT NULL FROM audit_auditevent WHERE id = %s", [eid])
        assert cur.fetchone()[0] is True
        conn.rollback()


# ------------------------------------------------------------------ L5 recovery code step-up
def test_l5_step_up_with_a_recovery_code_is_single_use_and_audited():
    from apps.identity.services.mfa import _new_recovery_codes

    person = make_user("p@example.com", mfa=True)
    codes = _new_recovery_codes(person.user)
    api = Api()
    api.login(person)
    assert api.post(STEP_UP, {"password": PASSWORD, "recovery_code": codes[0]}).status_code == 200
    assert api.post(STEP_UP, {"password": PASSWORD, "recovery_code": codes[0]}).status_code == 401
    assert (
        api.post(STEP_UP, {"password": WRONG_PASSWORD, "recovery_code": codes[1]}).status_code
        == 401
    )  # password still required
    event = AuditEvent.objects.get(action="identity.mfa.recovery_code_used")
    assert event.metadata == {"remaining": 9, "purpose": "step_up"}
    assert codes[0] not in repr(list(AuditEvent.objects.values()))
    both = api.post(STEP_UP, {"password": PASSWORD, "code": "123456", "recovery_code": codes[2]})
    assert both.status_code == 400


# ------------------------------------------------------------------ I1 rollback safeguard
def test_i1_audit_migration_rollback_is_refused_by_default_and_in_production(settings):
    from importlib import import_module

    guard = import_module("apps.audit.migrations.0003_ip_side_table_integrity").refuse_rollback
    with pytest.raises(RuntimeError, match="Refusing"):
        guard(None, None)
    settings.ERP_ALLOW_AUDIT_ROLLBACK = True
    settings.APP_ENVIRONMENT = "production"
    with pytest.raises(RuntimeError, match="Refusing"):
        guard(None, None)
    settings.APP_ENVIRONMENT = "local"
    guard(None, None)  # disposable dev database: allowed


# ------------------------------------------------------------------ key rotation as owner (L4)
ROTATION_SETUP = """
from django.test import RequestFactory
from apps.audit.services import record
from apps.identity.models import User
from tests.helpers import make_user
p = make_user("rot@example.com", mfa=True)
req = RequestFactory().get("/", REMOTE_ADDR="203.0.113.77")
record("identity.logout", actor=p.user, request=req)
"""
ROTATION_VERIFY = """
from apps.audit.models import AuditEventIP
from apps.audit.services import events_from_ip
from apps.core import crypto
from apps.identity.models import MFADevice
assert crypto.key_id_of(bytes(MFADevice.objects.get().secret_encrypted)) == "rot2"
assert crypto.key_id_of(bytes(AuditEventIP.objects.get().ip_encrypted)) == "rot2"
assert events_from_ip("203.0.113.77")
print("ROTATION-OK")
"""


def test_l4_key_rotation_and_index_rebuild_work_as_the_owner_role(owner_dsn):
    """Real commands, real owner connection, on a throwaway migrated database."""
    import base64

    backend = Path(__file__).resolve().parents[1]
    name = f"erp_rotation_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(**owner_dsn, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}" TEMPLATE template1')
    owner_url = (
        f"postgres://{owner_dsn['user']}:{owner_dsn['password']}@{owner_dsn['host']}:"
        f"{owner_dsn['port']}/{name}"
    )
    old = "rot1:" + base64.urlsafe_b64encode(b"o" * 32).decode()
    new = "rot2:" + base64.urlsafe_b64encode(b"N" * 32).decode()
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.test",
        "DATABASE_MIGRATION_URL": owner_url,
        "FIELD_ENCRYPTION_KEYS": old,
    }

    def manage(*args, **extra):
        result = subprocess.run(  # noqa: S603 - fixed interpreter and arguments
            [sys.executable, "manage.py", *args],
            cwd=backend,
            env={**env, **extra},
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    try:
        manage("migrate", "--noinput")
        manage("seed_roles")
        manage("shell", "-c", ROTATION_SETUP)
        manage("rotate_field_encryption", FIELD_ENCRYPTION_KEYS=f"{new},{old}")
        index_key = base64.urlsafe_b64encode(b"X" * 32).decode()
        manage("rebuild_ip_index", FIELD_ENCRYPTION_KEYS=f"{new},{old}", IP_INDEX_KEY=index_key)
        out = manage(
            "shell", "-c", ROTATION_VERIFY, FIELD_ENCRYPTION_KEYS=new, IP_INDEX_KEY=index_key
        )
        assert "ROTATION-OK" in out
    finally:
        with psycopg.connect(**owner_dsn, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
