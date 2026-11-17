"""Session security middleware (plan §6.7): revocation, idle and absolute timeouts.

Runs after ``AuthenticationMiddleware``. For an authenticated session it:

1. rejects the session if its ``SessionRecord`` is missing or revoked (revocation is effective
   on the very next request, whatever the session store holds);
2. ends it after 30 minutes idle or 12 hours since login (settings), auditing the expiry;
3. records activity at most once per minute (bounded writes).
"""

from collections.abc import Callable

from django.conf import settings
from django.contrib.auth import logout as django_logout
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from apps.audit.services import record as audit
from apps.identity import session_state as state
from apps.identity.models import SessionRecord
from apps.identity.services.sessions import current_record

_TOUCH_INTERVAL = 60


class SessionSecurityMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.user.is_authenticated:
            self._enforce(request)
        return self.get_response(request)

    def _expire(self, request: HttpRequest, record: SessionRecord | None, reason: str) -> None:
        user = request.user if request.user.is_authenticated else None
        if record is not None and record.revoked_at is None:
            record.revoked_at = timezone.now()
            record.revoke_reason = reason
            record.session_key_encrypted = None
            record.save(
                update_fields=["revoked_at", "revoke_reason", "session_key_encrypted", "updated_at"]
            )
        if reason in ("expired_idle", "expired_absolute"):
            audit(f"identity.session.{reason}", actor=user, request=request)
        django_logout(request)

    def _enforce(self, request: HttpRequest) -> None:
        record = current_record(request)
        if record is None or record.revoked_at is not None or record.user_id != request.user.pk:
            django_logout(request)
            return
        # For the session-host binding that runs next (Phase 3 plan §8.2): no second lookup.
        request.session_record = record  # type: ignore[attr-defined]
        now = state.now_ts()
        auth_at = int(request.session.get(state.AUTH_AT, 0))
        last = int(request.session.get(state.LAST_ACTIVITY, 0))
        if now - auth_at > settings.SESSION_ABSOLUTE_TIMEOUT_SECONDS:
            self._expire(request, record, "expired_absolute")
            return
        if now - last > settings.SESSION_IDLE_TIMEOUT_SECONDS:
            self._expire(request, record, "expired_idle")
            return
        if now - last >= _TOUCH_INTERVAL:
            request.session[state.LAST_ACTIVITY] = now
            SessionRecord.objects.filter(pk=record.pk).update(last_seen_at=timezone.now())
