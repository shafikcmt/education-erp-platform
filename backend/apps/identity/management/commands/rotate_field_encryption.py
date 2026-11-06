"""Re-encrypt every encrypted field with the current primary key (ADR-031 key rotation).

Procedure: put the new key FIRST in ``FIELD_ENCRYPTION_KEYS`` (keep the old ones), deploy, run
this command, verify, then remove the old key. Idempotent; values already under the primary key
are skipped. Plaintext never leaves the process and is never printed. Runs as the owner role
(ops/migrate container): the runtime role may not rewrite audit IP evidence (review L4).
"""

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.audit.models import AuditEventIP
from apps.core import crypto
from apps.core.db_operations import require_owner_role
from apps.core.ip_privacy import IP_PURPOSE
from apps.identity.models import MFADevice, SessionRecord
from apps.identity.services.sessions import _KEY_PURPOSE as SESSION_KEY_PURPOSE


def _rotate(blob: bytes | memoryview | None, purpose: str, primary: str) -> bytes | None:
    if not blob:
        return None
    data = bytes(blob)
    if crypto.key_id_of(data) == primary:
        return None
    return crypto.encrypt(crypto.decrypt(data, purpose=purpose), purpose=purpose)


class Command(BaseCommand):
    help = "Re-encrypt MFA secrets, session keys and IPs with the primary key."

    def handle(self, *args: Any, **options: Any) -> None:
        require_owner_role("rotate_field_encryption")
        primary = crypto.key_ring().primary_id
        counts = {"mfa": 0, "session": 0, "audit_ip": 0}
        with transaction.atomic():
            for device in MFADevice.objects.select_for_update():
                purpose = f"identity.mfadevice.secret:{device.pk}"
                new = _rotate(device.secret_encrypted, purpose, primary)
                if new:
                    MFADevice.objects.filter(pk=device.pk).update(secret_encrypted=new)
                    counts["mfa"] += 1
            for rec in SessionRecord.objects.select_for_update():
                ip = _rotate(rec.ip_encrypted, IP_PURPOSE, primary)
                key = _rotate(rec.session_key_encrypted, SESSION_KEY_PURPOSE, primary)
                updates: dict[str, bytes] = {}
                if ip:
                    updates["ip_encrypted"] = ip
                if key:
                    updates["session_key_encrypted"] = key
                if updates:
                    SessionRecord.objects.filter(pk=rec.pk).update(**updates)
                    counts["session"] += 1
            for row in AuditEventIP.objects.select_for_update():
                new = _rotate(row.ip_encrypted, IP_PURPOSE, primary)
                if new:
                    AuditEventIP.objects.filter(pk=row.pk).update(ip_encrypted=new)
                    counts["audit_ip"] += 1
        self.stdout.write(f"re-encrypted with key {primary!r}: {counts}")
