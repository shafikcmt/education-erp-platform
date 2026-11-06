"""Login, MFA challenge, step-up and logout (plan §6.1, §6.2, §6.6, §6.11).

No user enumeration: unknown email, wrong password, inactive and unactivated accounts all raise
the same :class:`~apps.identity.errors.InvalidCredentials` after equal work (see the backend).
Throttles key on HMACs of IP and normalised email, so they behave identically whether or not an
account exists. Failed attempts are audited without the submitted email or password.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.audit.services import record as audit
from apps.core import crypto
from apps.core.net import client_ip, user_agent_summary
from apps.identity import errors, throttling
from apps.identity import session_state as state
from apps.identity.models import SeenDevice, User
from apps.identity.services import mfa, sessions
from apps.identity.services.notifications import send_security_email
from apps.rbac.engine import user_requires_mfa

if TYPE_CHECKING:
    pass


class LoginStatus(StrEnum):
    AUTHENTICATED = "authenticated"
    MFA_REQUIRED = "mfa_required"
    MFA_ENROLLMENT_REQUIRED = "mfa_enrollment_required"


@dataclass(frozen=True)
class LoginResult:
    status: LoginStatus
    user: User | None = None


def _ip_subject(request: HttpRequest) -> str:
    return throttling.subject_key("ip", client_ip(request) or "unknown")


def _email_subject(email: str) -> str:
    return throttling.subject_key("email", email)


def login_with_password(request: HttpRequest, email: str, password: str) -> LoginResult:
    ip_bucket = throttling.Bucket.named("login_ip")
    ip_subject = _ip_subject(request)
    if ip_bucket.hit(ip_subject) > ip_bucket.limit:
        audit(
            "identity.login.throttled", request=request, outcome="denied", metadata={"bucket": "ip"}
        )
        raise errors.RateLimited(ip_bucket.retry_after(ip_subject))
    email_subject = _email_subject(email)
    wait = throttling.login_blocked_for(email_subject)
    if wait:
        audit(
            "identity.login.throttled",
            request=request,
            outcome="denied",
            metadata={"bucket": "email"},
        )
        raise errors.RateLimited(wait)

    user = authenticate(request, username=email, password=password)
    if user is None:
        locked = throttling.register_login_failure(email_subject)
        audit(
            "identity.login.failed",
            request=request,
            outcome="failure",
            metadata={"reason": "invalid_credentials"},
        )
        if locked:
            _on_lock(request, email)
        raise errors.InvalidCredentials()
    assert isinstance(user, User)  # noqa: S101 - EmailBackend returns identity.User
    throttling.clear_login_failures(email_subject)

    if mfa.has_mfa(user):
        request.session.cycle_key()
        request.session[state.PENDING_AUTH] = {
            "user_id": str(user.pk),
            "started_at": state.now_ts(),
            "attempts": 0,
        }
        return LoginResult(LoginStatus.MFA_REQUIRED, user)
    _complete_login(request, user, mfa_verified=False, method="password")
    if user_requires_mfa(user, use_cache=False):
        return LoginResult(LoginStatus.MFA_ENROLLMENT_REQUIRED, user)
    return LoginResult(LoginStatus.AUTHENTICATED, user)


def _on_lock(request: HttpRequest, email: str) -> None:
    audit(
        "identity.login.locked",
        request=request,
        outcome="denied",
        metadata={"reason": "too_many_failures"},
    )
    user = User.objects.filter(email__iexact=email.strip()).first()
    if user is not None and user.can_sign_in:
        send_security_email("lockout_notice", to=user.email, user=user)


def verify_mfa(request: HttpRequest, *, code: str = "", recovery_code: str = "") -> User:
    pending = request.session.get(state.PENDING_AUTH)
    if not pending:
        raise errors.MfaChallengeExpired()
    limit, ttl = settings.SECURITY_THROTTLES["mfa_attempts"]
    if state.now_ts() - int(pending["started_at"]) > ttl or int(pending["attempts"]) >= limit:
        request.session.pop(state.PENDING_AUTH, None)
        raise errors.MfaChallengeExpired()
    user = User.objects.filter(pk=pending["user_id"]).first()
    device = mfa.confirmed_device(user) if user is not None else None
    if user is None or device is None or not user.can_sign_in:
        request.session.pop(state.PENDING_AUTH, None)
        raise errors.MfaChallengeExpired()

    if recovery_code:
        remaining = mfa.use_recovery_code(user, recovery_code)
        ok = remaining is not None
    else:
        ok = mfa.verify_totp(device, code)
        remaining = None
    if not ok:
        pending["attempts"] = int(pending["attempts"]) + 1
        request.session[state.PENDING_AUTH] = pending
        audit(
            "identity.mfa.challenge_failed",
            actor_user_id=user.pk,
            request=request,
            outcome="failure",
            metadata={"reason": "recovery_code" if recovery_code else "totp"},
        )
        if pending["attempts"] >= limit:
            request.session.pop(state.PENDING_AUTH, None)
            raise errors.MfaChallengeExpired()
        raise errors.InvalidMfaCode()
    if remaining is not None:
        audit(
            "identity.mfa.recovery_code_used",
            actor=user,
            request=request,
            metadata={"remaining": remaining},
        )
    _complete_login(
        request, user, mfa_verified=True, method="recovery_code" if recovery_code else "totp"
    )
    return user


def _complete_login(request: HttpRequest, user: User, *, mfa_verified: bool, method: str) -> None:
    with transaction.atomic():
        sessions.start_session(request, user, mfa_verified=mfa_verified)
        audit(
            "identity.login.succeeded",
            actor=user,
            request=request,
            metadata={"mfa": mfa_verified, "method": method},
        )
    _note_device(request, user)


# ------------------------------------------------------------------ new sign-in notices
def _notify_policy_applies(user: User) -> bool:
    policy = settings.SECURITY_NOTIFY_NEW_SIGNIN
    if policy == "all":
        return True
    if policy == "platform_staff":
        return user.platform_roles.exists()
    if policy == "privileged":
        return user_requires_mfa(user)
    return False


def _note_device(request: HttpRequest, user: User) -> None:
    family = user_agent_summary(request.META.get("HTTP_USER_AGENT", ""))
    fingerprint = crypto.blind_index(
        f"{family}|{client_ip(request)}", purpose="identity.seendevice"
    )
    now = timezone.now()
    horizon = now - timedelta(days=settings.SECURITY_SEEN_DEVICE_DAYS)
    first_ever = not SeenDevice.objects.filter(user=user).exists()
    device, created = SeenDevice.objects.get_or_create(
        user=user,
        fingerprint_hmac=fingerprint,
        defaults={"first_seen_at": now, "last_seen_at": now},
    )
    is_new = created or device.last_seen_at < horizon
    if not created:
        device.last_seen_at = now
        device.save(update_fields=["last_seen_at", "updated_at"])
    # The very first sign-in after activation is expected and not reported.
    if is_new and not first_ever and _notify_policy_applies(user):
        send_security_email("new_signin", to=user.email, user=user, context={"device": family})
        audit("identity.signin.new_device_notified", actor=user, request=request)


# ------------------------------------------------------------------ step-up and logout
def step_up(request: HttpRequest, user: User, *, password: str, code: str = "") -> None:
    """Re-authenticate (password + current MFA code if enrolled) for 10 minutes (ADR-035)."""
    bucket = throttling.Bucket.named("step_up")
    subject = throttling.subject_key("step_up", str(user.pk))
    if bucket.exceeded(subject):
        audit(
            "identity.step_up.failed",
            actor=user,
            request=request,
            outcome="denied",
            metadata={"reason": "throttled"},
        )
        raise errors.RateLimited(bucket.retry_after(subject))
    device = mfa.confirmed_device(user)
    reason = ""
    if not user.check_password(password):
        reason = "password"
    elif device is not None and not mfa.verify_totp(device, code):
        reason = "mfa"
    if reason:
        bucket.hit(subject)
        audit(
            "identity.step_up.failed",
            actor=user,
            request=request,
            outcome="failure",
            metadata={"reason": reason},
        )
        raise errors.InvalidCredentials("The password or verification code is incorrect.")
    bucket.reset(subject)
    sessions.mark_step_up(request)
    audit("identity.step_up.succeeded", actor=user, request=request)


def logout(request: HttpRequest) -> None:
    user = request.user
    if user.is_authenticated:
        audit("identity.logout", actor=user, request=request)
    sessions.end_session(request, reason="logout")
