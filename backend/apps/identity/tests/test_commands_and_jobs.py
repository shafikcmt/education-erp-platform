"""Bootstrap, erasure, key rotation, housekeeping, sealed email tasks, new sign-in notices."""

import base64
import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core import mail
from django.core.management import CommandError, call_command
from django.test import override_settings
from django.utils import timezone

from apps.audit.models import AuditEvent, AuditEventIP
from apps.audit.services import record
from apps.core import crypto
from apps.identity.models import AccountToken, MFADevice, SessionRecord, User
from apps.identity.services import notifications
from apps.identity.services.maintenance import run_housekeeping
from apps.rbac.models import PlatformRoleAssignment
from tests.helpers import Api, link_token, make_user

pytestmark = pytest.mark.django_db


def test_create_platform_admin_bootstrap_flow():
    out = StringIO()
    call_command("create_platform_admin", "--email", "Owner@Example.com", stdout=out)
    user = User.objects.get(email="owner@example.com")
    assert user.activated_at is None and not user.has_usable_password()
    assert PlatformRoleAssignment.objects.filter(user=user, role__code="super_admin").exists()
    token = link_token(mail.outbox[-1])
    assert token not in out.getvalue()
    assert AuditEvent.objects.filter(
        action="identity.account.created", metadata__source="bootstrap_command"
    ).exists()
    # A Super Admin now exists (once activated): refuse to create another.
    user.activated_at = timezone.now()
    user.save()
    with pytest.raises(CommandError):
        call_command("create_platform_admin", "--email", "second@example.com")


def test_erase_ip_data_command():
    person = make_user()
    api = Api(remote_addr="203.0.113.44")
    api.login(person)
    assert AuditEventIP.objects.filter(event__actor_user_id=person.user.pk).exists()
    out = StringIO()
    call_command("erase_ip_data", "--user", str(person.user.pk), stdout=out)
    assert not AuditEventIP.objects.filter(event__actor_user_id=person.user.pk).exists()
    record_row = SessionRecord.objects.get(user=person.user)
    assert record_row.ip_encrypted is None and record_row.ip_prefix == ""
    assert AuditEvent.objects.filter(action="audit.ip.erased").exists()
    with pytest.raises(CommandError):
        call_command("erase_ip_data", "--user", "nope")


def test_rotate_field_encryption_and_rebuild_index():
    person = make_user(mfa=True)
    api = Api(remote_addr="203.0.113.45")
    api.login(person)
    new_key = "rot1:" + base64.urlsafe_b64encode(b"r" * 32).decode()
    from django.conf import settings

    ring = [new_key, *settings.FIELD_ENCRYPTION_KEYS]
    with override_settings(FIELD_ENCRYPTION_KEYS=ring):
        call_command("rotate_field_encryption", stdout=StringIO())
        device = MFADevice.objects.get(user=person.user)
        assert crypto.key_id_of(bytes(device.secret_encrypted)) == "rot1"
        session = SessionRecord.objects.get(user=person.user)
        assert crypto.key_id_of(bytes(session.ip_encrypted or b"")) == "rot1"
        assert api.get("/api/v1/me/").status_code == 200  # still decryptable
    new_index_key = base64.urlsafe_b64encode(b"n" * 32).decode()
    with override_settings(FIELD_ENCRYPTION_KEYS=ring, IP_INDEX_KEY=new_index_key):
        call_command("rebuild_ip_index", stdout=StringIO())
        from apps.audit.services import events_from_ip

        assert events_from_ip("203.0.113.45")


def test_housekeeping_anonymises_old_session_ips_and_purges_tokens():
    person = make_user()
    Api().login(person)
    SessionRecord.objects.update(created_at=timezone.now() - timedelta(days=400))
    AccountToken.objects.create(
        user=person.user,
        purpose="password_reset",
        token_hash="0" * 64,
        expires_at=timezone.now() - timedelta(days=8),
    )
    result = run_housekeeping()
    assert result == {"session_ips_anonymized": 1, "tokens_purged": 1}
    row = SessionRecord.objects.get(user=person.user)
    assert row.ip_encrypted is None and row.ip_prefix == "198.51.100.0/24"


def test_celery_tasks_run():
    from apps.audit.tasks import anonymize_expired_ips
    from apps.identity.tasks import housekeeping

    assert anonymize_expired_ips.delay().get() == 0
    assert housekeeping.delay().get() == {"session_ips_anonymized": 0, "tokens_purged": 0}


def test_email_task_payload_is_sealed(monkeypatch):
    captured = {}

    def fake_delay(sealed_hex):
        captured["payload"] = sealed_hex

    from apps.identity import tasks

    monkeypatch.setattr(tasks.deliver_security_email, "delay", fake_delay)
    user = make_user().user
    notifications.send_security_email(
        "activation",
        to=user.email,
        user=user,
        context={"action_url": "https://x/#token=RAWTOKEN123"},
    )
    sealed = bytes.fromhex(captured["payload"])
    assert b"RAWTOKEN123" not in sealed and b"activation" not in sealed
    payload = json.loads(crypto.decrypt(sealed, purpose="identity.email.task"))
    assert payload["context"]["action_url"].endswith("RAWTOKEN123")
    with pytest.raises(ValueError, match="Unknown email template"):
        notifications.send_security_email("unknown", to=user.email, user=user)


def test_new_signin_notice_for_platform_staff_only_on_new_devices():
    staff = make_user("staff@example.com", roles=("platform_support",), mfa=True)
    with override_settings(SECURITY_NOTIFY_NEW_SIGNIN="platform_staff"):
        from freezegun import freeze_time

        with freeze_time("2026-11-06 10:00:00") as clock:
            Api(remote_addr="203.0.113.1").login(staff)  # first ever: no notice
            clock.tick(31)
            Api(remote_addr="203.0.113.1").login(staff)  # same device: no notice
            clock.tick(31)
            Api(remote_addr="192.0.2.99", user_agent="Mozilla/5.0 (iPhone) Safari/604.1").login(
                staff
            )
    notices = [m for m in mail.outbox if "new sign-in" in m.subject.lower()]
    assert len(notices) == 1
    body = notices[0].body
    assert "192.0.2.99" not in body and "Safari on iOS" in body
    assert AuditEvent.objects.filter(action="identity.signin.new_device_notified").count() == 1

    plain = make_user("plain@example.com")
    Api(remote_addr="203.0.113.2").login(plain)
    Api(remote_addr="192.0.2.5").login(plain)
    assert len([m for m in mail.outbox if "new sign-in" in m.subject.lower()]) == 1


def test_bengali_templates_render_for_bn_users():
    user = make_user("bn@example.com", locale="bn").user
    notifications.send_security_email("password_changed", to=user.email, user=user)
    assert "পাসওয়ার্ড" in mail.outbox[-1].subject


def test_every_template_exists_in_both_languages():
    from pathlib import Path

    folder = Path(notifications.__file__).resolve().parents[1] / "templates/identity/email"
    for name in notifications.TEMPLATES:
        for locale in ("en", "bn"):
            for part in ("subject", "body"):
                assert (folder / f"{name}.{locale}.{part}.txt").exists(), (name, locale, part)


def test_audit_record_without_request_has_no_ip():
    event = record("identity.logout")
    assert not AuditEventIP.objects.filter(event=event).exists()
