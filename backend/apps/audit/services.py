"""Writing, revealing and anonymising audit data.

``record()`` writes in the caller's transaction; when the write fails, the exception
propagates, so the security action fails too (fail closed, plan §6.8).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.audit.events import allowed_metadata
from apps.audit.models import ActorType, AuditEvent, AuditEventIP, Outcome
from apps.core.ip_privacy import ip_search_index, open_ip, seal_ip
from apps.core.logging import _is_sensitive
from apps.core.middleware import get_request_id
from apps.core.net import client_ip, user_agent_summary

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

_MAX_STR = 200
_MAX_LIST = 50

Scalar = str | int | bool | None


def _clean_metadata(action: str, metadata: dict[str, Any] | None) -> dict[str, Any]:
    allowed = allowed_metadata(action)
    cleaned: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        if key not in allowed or _is_sensitive(key):
            raise ValueError(f"Metadata key {key!r} is not allow-listed for {action!r}")
        if isinstance(value, list | tuple):
            if len(value) > _MAX_LIST or not all(isinstance(v, str | int) for v in value):
                raise ValueError(f"Metadata {key!r} must be a short list of scalars")
            cleaned[key] = [str(v)[:_MAX_STR] if isinstance(v, str) else v for v in value]
        elif value is None or isinstance(value, bool | int):
            cleaned[key] = value
        elif isinstance(value, str | uuid.UUID):
            cleaned[key] = str(value)[:_MAX_STR]
        else:
            raise ValueError(f"Metadata {key!r} must be a scalar")
    return cleaned


def record(
    action: str,
    *,
    outcome: str = Outcome.SUCCESS,
    actor: AbstractBaseUser | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_type: str | None = None,
    target_type: str = "",
    target_id: uuid.UUID | str | None = None,
    metadata: dict[str, Any] | None = None,
    request: HttpRequest | None = None,
    tenant_id: uuid.UUID | None = None,
    support_session_id: uuid.UUID | None = None,
) -> AuditEvent:
    """Append one audit event (and its encrypted IP, when a request is given)."""
    cleaned = _clean_metadata(action, metadata)
    if actor is not None and getattr(actor, "is_authenticated", False):
        actor_user_id = actor.pk
    if actor_type is None:
        actor_type = ActorType.USER if actor_user_id else ActorType.SYSTEM
    now = timezone.now()
    ua = user_agent_summary(request.META.get("HTTP_USER_AGENT", "")) if request else ""
    with transaction.atomic():
        event = AuditEvent.objects.create(
            occurred_at=now,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            support_session_id=support_session_id,
            action=action,
            outcome=outcome,
            target_type=target_type,
            target_id=str(target_id) if target_id else "",
            metadata=cleaned,
            user_agent_summary=ua,
            request_id=get_request_id(request) if request else "",
        )
        ip = client_ip(request) if request else ""
        if ip:
            sealed = seal_ip(ip)
            AuditEventIP.objects.create(
                event=event,
                ip_encrypted=sealed.ip_encrypted,
                ip_index=sealed.ip_index,
                ip_prefix=sealed.ip_prefix,
                created_at=now,
            )
    return event


def reveal_ip(event: AuditEvent, *, actor: AbstractBaseUser, request: HttpRequest) -> str:
    """Decrypt an event's IP and audit the reveal. ``audit.event.view_ip`` is re-checked here
    (L2); the API view additionally enforces MFA and step-up."""
    from apps.rbac.engine import require_perm

    require_perm(actor, "audit.event.view_ip", use_cache=False)
    side = AuditEventIP.objects.filter(event=event).first()
    value = open_ip(side.ip_encrypted) if side else ""
    record(
        "audit.ip.revealed",
        actor=actor,
        request=request,
        target_type="audit.event",
        target_id=event.pk,
        metadata={"event_id": str(event.pk)},
    )
    return value


def events_from_ip(ip: str) -> list[uuid.UUID]:
    """Exact-match forensic search via the blind index (no decryption)."""
    index = ip_search_index(ip)
    return list(AuditEventIP.objects.filter(ip_index=index).values_list("event_id", flat=True))


def anonymize_expired_ips(*, now: datetime | None = None) -> int:
    """ADR-036 retention: drop ciphertext and blind index, keep only the network prefix."""
    cutoff = (now or timezone.now()) - timedelta(days=settings.SECURITY_IP_RETENTION_DAYS)
    return AuditEventIP.objects.filter(created_at__lt=cutoff, anonymized_at__isnull=True).update(
        ip_encrypted=None, ip_index=None, anonymized_at=timezone.now()
    )


def erase_ips_for_actor(user_id: uuid.UUID, *, before: datetime | None = None) -> int:
    """Data-subject erasure: delete the IP rows of every event this user performed."""
    events = AuditEvent.objects.filter(actor_user_id=user_id)
    if before is not None:
        events = events.filter(occurred_at__lt=before)
    deleted, _ = AuditEventIP.objects.filter(event__in=events).delete()
    return int(deleted)
