"""Daily identity housekeeping and IP erasure (ADR-036; platform tasks)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.identity.models import AccountToken, SeenDevice, SessionRecord

# IP-derived device fingerprints (HMAC of browser family + IP) are kept at most 90 days (M4).
SEEN_DEVICE_MAX_DAYS = 90


def anonymize_session_ips(*, now: datetime | None = None) -> int:
    cutoff = (now or timezone.now()) - timedelta(days=settings.SECURITY_IP_RETENTION_DAYS)
    return (
        SessionRecord.objects.filter(created_at__lt=cutoff)
        .filter(Q(ip_encrypted__isnull=False) | Q(ip_index__isnull=False))
        .update(ip_encrypted=None, ip_index=None)
    )


def purge_expired_tokens(*, now: datetime | None = None) -> int:
    cutoff = (now or timezone.now()) - timedelta(days=7)
    deleted, _ = AccountToken.objects.filter(expires_at__lt=cutoff).delete()
    return int(deleted)


def purge_seen_devices(*, now: datetime | None = None) -> int:
    days = min(SEEN_DEVICE_MAX_DAYS, settings.SECURITY_SEEN_DEVICE_DAYS)
    cutoff = (now or timezone.now()) - timedelta(days=days)
    deleted, _ = SeenDevice.objects.filter(last_seen_at__lt=cutoff).delete()
    return int(deleted)


def close_expired_sessions(*, now: datetime | None = None) -> int:
    """L1: sessions older than the absolute lifetime are closed and their encrypted Django
    session keys dropped, even when the browser never came back to trigger the middleware."""
    from apps.identity.services.sessions import revoke_records

    cutoff = (now or timezone.now()) - timedelta(seconds=settings.SESSION_ABSOLUTE_TIMEOUT_SECONDS)
    return revoke_records(
        SessionRecord.objects.filter(created_at__lt=cutoff), reason="expired_absolute"
    )


def run_housekeeping() -> dict[str, int]:
    return {
        "session_ips_anonymized": anonymize_session_ips(),
        "tokens_purged": purge_expired_tokens(),
        "seen_devices_purged": purge_seen_devices(),
        "sessions_closed": close_expired_sessions(),
    }


def erase_session_ips(user_id: uuid.UUID, *, before: datetime | None = None) -> int:
    """Data-subject erasure for session records: drops ciphertext, index **and** prefix."""
    records = SessionRecord.objects.filter(user_id=user_id)
    if before is not None:
        records = records.filter(created_at__lt=before)
    return records.update(ip_encrypted=None, ip_index=None, ip_prefix="")


def erase_seen_devices(user_id: uuid.UUID, *, before: datetime | None = None) -> int:
    """Data-subject erasure for IP-derived device fingerprints (M4)."""
    devices = SeenDevice.objects.filter(user_id=user_id)
    if before is not None:
        devices = devices.filter(first_seen_at__lt=before)
    deleted, _ = devices.delete()
    return int(deleted)
