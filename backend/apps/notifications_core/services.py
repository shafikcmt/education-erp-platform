"""Notification dispatch (Phase 5 M4; ADR-059).

:func:`notify` runs inside the tenant's transaction: it writes one in-app row per active member
and, when asked, queues an email per row after commit (tenant task). Only active memberships of
the current tenant receive anything (RLS + status filter). Links are relative paths only.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from django.db import transaction
from django.utils import timezone

from apps.notifications_core.models import Notification


def notify(
    membership_ids: Iterable[uuid.UUID],
    *,
    kind: str,
    title: str,
    body: str = "",
    link: str = "",
    email: bool = False,
) -> list[Notification]:
    from apps.tenancy.models import Membership

    if link and not link.startswith("/"):
        raise ValueError("Notification links are relative paths.")
    active = list(
        Membership.objects.filter(
            pk__in=set(membership_ids), status=Membership.Status.ACTIVE
        ).values_list("pk", flat=True)
    )
    rows = Notification.objects.bulk_create(
        [
            Notification(
                membership_id=pk, kind=kind, title=title[:200], body=body[:1000], link=link
            )
            for pk in active
        ]
    )
    if email and rows:
        from apps.core.tenancy import require_tenant
        from apps.notifications_core.tasks import deliver_email

        tenant_id = str(require_tenant().id)
        ids = [str(r.pk) for r in rows]
        transaction.on_commit(
            lambda: [deliver_email.delay(tenant_id=tenant_id, notification_id=i) for i in ids]
        )
    return rows


def mark_read(*, membership_id: uuid.UUID, notification_ids: Iterable[uuid.UUID]) -> int:
    return Notification.objects.filter(
        membership_id=membership_id, pk__in=set(notification_ids), read_at__isnull=True
    ).update(read_at=timezone.now(), updated_at=timezone.now())


def unread_count(membership_id: uuid.UUID) -> int:
    return Notification.objects.filter(membership_id=membership_id, read_at__isnull=True).count()
