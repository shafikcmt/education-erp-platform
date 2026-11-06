"""Daily identity housekeeping and IP erasure (ADR-036; platform tasks)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.identity.models import AccountToken, SessionRecord


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


def run_housekeeping() -> dict[str, int]:
    return {
        "session_ips_anonymized": anonymize_session_ips(),
        "tokens_purged": purge_expired_tokens(),
    }


def erase_session_ips(user_id: uuid.UUID, *, before: datetime | None = None) -> int:
    """Data-subject erasure for session records: drops ciphertext, index **and** prefix."""
    records = SessionRecord.objects.filter(user_id=user_id)
    if before is not None:
        records = records.filter(created_at__lt=before)
    return records.update(ip_encrypted=None, ip_index=None, ip_prefix="")
