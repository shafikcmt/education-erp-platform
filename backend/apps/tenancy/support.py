"""Support sessions: lookup and lifecycle helpers shared by the request path, the permission
source and the services (Phase 3 M5; plan §11; ADR-045).

A session is **usable** when it is ``approved`` or ``active`` and ``starts_at <= now <
ends_at``. Everything here runs inside the tenant transaction of the request host, so RLS
limits every lookup to that tenant's sessions (S2): a session approved for tenant A does not
exist on tenant B's host.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db.models import Q
from django.utils import timezone

from apps.tenancy.models import SupportSession

USABLE_STATUSES = (SupportSession.Status.APPROVED, SupportSession.Status.ACTIVE)


def usable_session(user_id: Any) -> SupportSession | None:
    """The actor's usable session in the current tenant, or ``None``."""
    if user_id is None:
        return None
    now = timezone.now()
    found: SupportSession | None = (
        SupportSession.objects.filter(
            staff_user_id=user_id,
            status__in=USABLE_STATUSES,
            starts_at__lte=now,
            ends_at__gt=now,
        )
        .order_by("-starts_at")
        .first()
    )
    return found


def lapsed_session(user_id: Any) -> SupportSession | None:
    """An approved/active session whose window has passed (expires lazily on first use)."""
    if user_id is None:
        return None
    return (
        SupportSession.objects.filter(
            staff_user_id=user_id, status__in=USABLE_STATUSES, ends_at__lte=timezone.now()
        )
        .order_by("-ends_at")
        .first()
    )


def ended_recently(user_id: Any) -> bool:
    """The actor had a session in this tenant that is over (ended, revoked or expired)."""
    if user_id is None:
        return False
    return SupportSession.objects.filter(
        Q(staff_user_id=user_id)
        & Q(
            status__in=(
                SupportSession.Status.ENDED,
                SupportSession.Status.REVOKED,
                SupportSession.Status.EXPIRED,
            )
        )
    ).exists()


def session_id(session: SupportSession | None) -> uuid.UUID | None:
    return session.pk if session is not None else None
