"""Email delivery of in-app notifications (Phase 5 M4; tenant task, ADR-042)."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from apps.tenancy.tasking import tenant_task


@tenant_task(name="notifications_core.deliver_email")
def deliver_email(*, tenant_id: uuid.UUID, notification_id: str) -> bool:
    from apps.notifications_core.models import Notification

    row = (
        Notification.objects.select_related("membership__user")
        .filter(pk=notification_id, email_sent_at__isnull=True)
        .first()
    )
    if row is None:
        return False
    body = row.body + (f"\n\n{row.link}" if row.link else "")
    send_mail(row.title, body, settings.DEFAULT_FROM_EMAIL, [row.membership.user.email])
    row.email_sent_at = timezone.now()
    row.save(update_fields=["email_sent_at", "updated_at"])
    return True
