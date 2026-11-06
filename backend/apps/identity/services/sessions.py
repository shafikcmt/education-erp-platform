"""Session lifecycle on top of Django's session framework (plan §6.7).

* ``start_session`` uses ``django.contrib.auth.login()`` (which rotates the key) and creates the
  ``SessionRecord`` index.
* ``rotate`` cycles the key on MFA completion and step-up and keeps the record in sync.
* Revocation marks the record and deletes the Django session; the middleware rejects any session
  whose record is missing or revoked.
"""

from __future__ import annotations

import uuid
from importlib import import_module
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone

from apps.audit.services import record as audit
from apps.core import crypto
from apps.core.ip_privacy import seal_ip
from apps.core.net import client_ip, user_agent_summary
from apps.core.tokens import hash_token
from apps.identity import session_state as state
from apps.identity.models import SessionRecord

if TYPE_CHECKING:
    from apps.identity.models import User

_KEY_PURPOSE = "identity.sessionrecord.session_key"


def _seal_key(session_key: str) -> bytes:
    return crypto.encrypt_str(session_key, purpose=_KEY_PURPOSE)


def current_record(request: HttpRequest) -> SessionRecord | None:
    key = request.session.session_key
    if not key:
        return None
    return SessionRecord.objects.filter(session_key_hash=hash_token(key)).first()


def start_session(request: HttpRequest, user: User, *, mfa_verified: bool) -> SessionRecord:
    """Log the user in (Django) and index the session. The key is rotated by ``login()``."""
    request.session.pop(state.PENDING_AUTH, None)
    django_login(request, user, backend="apps.identity.backends.EmailBackend")
    now = state.now_ts()
    request.session[state.AUTH_AT] = now
    request.session[state.LAST_ACTIVITY] = now
    request.session.pop(state.STEP_UP_AT, None)
    if mfa_verified:
        request.session[state.MFA_VERIFIED_AT] = now
    else:
        request.session.pop(state.MFA_VERIFIED_AT, None)
    request.session.save()
    key = request.session.session_key or ""
    sealed = seal_ip(client_ip(request))
    record = SessionRecord.objects.create(
        user=user,
        session_key_hash=hash_token(key),
        session_key_encrypted=_seal_key(key),
        host=request.get_host()[:255],
        last_seen_at=timezone.now(),
        mfa_verified_at=timezone.now() if mfa_verified else None,
        user_agent_summary=user_agent_summary(request.META.get("HTTP_USER_AGENT", "")),
        ip_encrypted=sealed.ip_encrypted,
        ip_index=sealed.ip_index,
        ip_prefix=sealed.ip_prefix,
    )
    request.session[state.RECORD_ID] = str(record.pk)
    return record


def rotate(request: HttpRequest) -> None:
    """Cycle the session key (fixation protection) and re-point the record to the new key."""
    record = current_record(request)
    request.session.cycle_key()
    request.session.save()
    if record is not None:
        key = request.session.session_key or ""
        record.session_key_hash = hash_token(key)
        record.session_key_encrypted = _seal_key(key)
        record.save(update_fields=["session_key_hash", "session_key_encrypted", "updated_at"])


def mark_mfa_verified(request: HttpRequest) -> None:
    request.session[state.MFA_VERIFIED_AT] = state.now_ts()
    rotate(request)
    if (record_id := _record_id(request)) is not None:
        SessionRecord.objects.filter(pk=record_id).update(mfa_verified_at=timezone.now())


def mark_step_up(request: HttpRequest) -> None:
    request.session[state.STEP_UP_AT] = state.now_ts()
    rotate(request)
    if (record_id := _record_id(request)) is not None:
        SessionRecord.objects.filter(pk=record_id).update(step_up_at=timezone.now())


def _record_id(request: HttpRequest) -> uuid.UUID | None:
    raw = request.session.get(state.RECORD_ID)
    try:
        return uuid.UUID(str(raw)) if raw else None
    except ValueError:
        return None


def _delete_django_session(record: SessionRecord) -> None:
    if not record.session_key_encrypted:
        return
    try:
        key = crypto.decrypt_str(record.session_key_encrypted, purpose=_KEY_PURPOSE)
    except crypto.DecryptionError:
        return
    engine = import_module(settings.SESSION_ENGINE)
    engine.SessionStore(session_key=key).delete()


def revoke_records(records: QuerySet[SessionRecord], *, reason: str) -> int:
    count = 0
    for record in records.filter(revoked_at__isnull=True):
        _delete_django_session(record)
        record.revoked_at = timezone.now()
        record.revoke_reason = reason[:40]
        record.session_key_encrypted = None
        record.save(
            update_fields=["revoked_at", "revoke_reason", "session_key_encrypted", "updated_at"]
        )
        count += 1
    return count


def revoke_user_sessions(
    user: User,
    *,
    reason: str,
    keep: HttpRequest | None = None,
    actor: User | None = None,
    request: HttpRequest | None = None,
) -> int:
    """Revoke every active session of ``user`` (except the one of ``keep``, if given)."""
    records = SessionRecord.objects.filter(user=user)
    if keep is not None and (keep_id := _record_id(keep)) is not None:
        records = records.exclude(pk=keep_id)
    count = revoke_records(records, reason=reason)
    if count:
        audit(
            "identity.session.revoked",
            actor=actor,
            request=request,
            target_type="identity.user",
            target_id=user.pk,
            metadata={"reason": reason, "count": count},
        )
    return count


def admin_revoke_sessions(actor: User, user: User, *, request: HttpRequest) -> int:
    """Admin "sign out everywhere": permission re-checked here (L2) and never on a more
    privileged account (H2)."""
    from apps.rbac.services import assert_can_act_on

    assert_can_act_on(actor, user, "identity.session.revoke_any")
    return revoke_user_sessions(user, reason="revoked_by_admin", actor=actor, request=request)


def revoke_one(user: User, record: SessionRecord, *, actor: User, request: HttpRequest) -> None:
    if revoke_records(SessionRecord.objects.filter(pk=record.pk, user=user), reason="revoked"):
        audit(
            "identity.session.revoked",
            actor=actor,
            request=request,
            target_type="identity.user",
            target_id=user.pk,
            metadata={"reason": "revoked_by_user", "count": 1},
        )


def end_session(request: HttpRequest, *, reason: str) -> None:
    """Revoke the current session's record and log out (Django ``logout`` flushes the session)."""
    record_id = _record_id(request)
    if record_id is not None:
        SessionRecord.objects.filter(pk=record_id, revoked_at__isnull=True).update(
            revoked_at=timezone.now(), revoke_reason=reason[:40], session_key_encrypted=None
        )
    django_logout(request)


def active_sessions(user: User) -> QuerySet[SessionRecord]:
    return SessionRecord.objects.filter(user=user, revoked_at__isnull=True).order_by(
        "-last_seen_at"
    )
