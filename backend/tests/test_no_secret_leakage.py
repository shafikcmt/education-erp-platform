"""Owner requirement 9 / plan §10: secrets never appear in logs, audit rows, Sentry events,
emails or later API responses. Runs the complete flow and scans every sink."""

import json
import logging

import pytest
from django.core import mail
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.core.observability import scrub_event
from apps.identity.models import MFADevice
from tests.helpers import Api, link_token

pytestmark = pytest.mark.django_db

NEW_PASSWORD = "Leak-Test-New-Pass-77"


def test_full_flow_leaks_no_secret_anywhere(admin_api, caplog):
    caplog.set_level(logging.DEBUG)
    secrets_seen: list[str] = []
    later_responses: list[str] = []

    # account creation + activation
    admin_api.post("/api/v1/platform/users/", {"email": "leak@example.com"})
    activation = link_token(mail.outbox[-1])
    secrets_seen.append(activation)
    api = Api()
    api.post("/api/v1/auth/activate/", {"token": activation, "password": NEW_PASSWORD})
    secrets_seen.append(NEW_PASSWORD)
    api.post("/api/v1/auth/login/", {"email": "leak@example.com", "password": NEW_PASSWORD})
    secrets_seen.append(api.client.cookies["sessionid"].value)
    secrets_seen.append(api.client.cookies["csrftoken"].value)

    # MFA enrollment incl. the one-time manual key
    api.post("/api/v1/auth/step-up/", {"password": NEW_PASSWORD})
    setup = api.post("/api/v1/me/mfa/totp/setup/").json()
    key = api.post(f"/api/v1/me/mfa/totp/setup/{setup['device_id']}/manual-key/").json()
    secret = key["manual_key"].replace(" ", "")
    secrets_seen.append(secret)
    import pyotp

    totp = pyotp.TOTP(secret)
    code = totp.generate_otp(totp.timecode(timezone.now()))
    secrets_seen.append(code)
    codes = api.post(
        "/api/v1/me/mfa/totp/confirm/", {"device_id": setup["device_id"], "code": code}
    ).json()["recovery_codes"]
    secrets_seen.extend(codes)
    secrets_seen.extend(c.replace("-", "") for c in codes)

    # password reset
    Api().post("/api/v1/auth/password/reset/", {"email": "leak@example.com"})
    reset = link_token(mail.outbox[-1])
    secrets_seen.append(reset)

    # later responses never return the secret or codes
    for path in ("/api/v1/me/", "/api/v1/me/mfa/", "/api/v1/me/sessions/"):
        later_responses.append(api.get(path).content.decode())
    later_responses.append(admin_api.get("/api/v1/platform/audit-events/").content.decode())
    later_responses.append(
        api.post(f"/api/v1/me/mfa/totp/setup/{setup['device_id']}/manual-key/").content.decode()
    )

    audit_dump = json.dumps(list(AuditEvent.objects.values()), default=str)
    logs = caplog.text
    # Emails may carry their own link token (that is their job) but never other secrets.
    email_bodies = [f"{m.subject}{m.body}" for m in mail.outbox]
    sentry = json.dumps(
        scrub_event(
            {
                "request": {
                    "url": "https://x/api/v1/auth/login/",
                    "data": {"password": NEW_PASSWORD},
                },
                "extra": {"manual_key": key["manual_key"], "recovery_codes": codes, "otp": code},
            }
        )
    )

    for value in secrets_seen:
        assert value not in audit_dump, f"audit leaks {value[:4]}…"
        assert value not in logs, f"logs leak {value[:4]}…"
        assert value not in sentry, f"sentry leaks {value[:4]}…"
        for response in later_responses:
            assert value not in response
        for body in email_bodies:
            if value in (activation, reset):
                continue
            assert value not in body, f"email leaks {value[:4]}…"
    assert "otpauth" not in audit_dump + logs
    raw_secret = bytes(MFADevice.objects.get(pk=setup["device_id"]).secret_encrypted)
    assert secret.encode() not in raw_secret
