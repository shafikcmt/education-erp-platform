"""Names and helpers for security state kept in the Django session (plan §6.1, §6.6, §6.7).

Django's session framework is the store (ADR-033); ``SessionRecord`` mirrors what the account
security page needs. Timestamps are stored as epoch seconds (JSON-serialisable).
"""

import time
from typing import Any

from django.conf import settings
from django.http import HttpRequest

PENDING_AUTH = "erp_pending_auth"  # {"user_id", "started_at", "attempts"} before MFA
AUTH_AT = "erp_auth_at"
LAST_ACTIVITY = "erp_last_activity"
MFA_VERIFIED_AT = "erp_mfa_verified_at"
STEP_UP_AT = "erp_step_up_at"
RECORD_ID = "erp_session_record_id"


def now_ts() -> int:
    return int(time.time())


def session(request: HttpRequest) -> Any:
    return request.session


def mfa_verified(request: HttpRequest) -> bool:
    return bool(request.session.get(MFA_VERIFIED_AT))


def step_up_fresh(request: HttpRequest) -> bool:
    at = request.session.get(STEP_UP_AT)
    return at is not None and now_ts() - int(at) <= settings.STEP_UP_TTL_SECONDS


def step_up_expires_at(request: HttpRequest) -> int | None:
    at = request.session.get(STEP_UP_AT)
    if not at or not step_up_fresh(request):
        return None
    return int(at) + settings.STEP_UP_TTL_SECONDS


def idle_expires_at(request: HttpRequest) -> int | None:
    last = request.session.get(LAST_ACTIVITY)
    return int(last) + settings.SESSION_IDLE_TIMEOUT_SECONDS if last else None


def absolute_expires_at(request: HttpRequest) -> int | None:
    auth_at = request.session.get(AUTH_AT)
    return int(auth_at) + settings.SESSION_ABSOLUTE_TIMEOUT_SECONDS if auth_at else None
