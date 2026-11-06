"""Account lifecycle: administrative creation, activation, password and email flows,
deactivation (plan §6.3-§6.5; ADR-034, ADR-037). No public registration.

Enumeration safety: the anonymous request endpoints (password reset, activation resend) always
return the same ``202`` response; only these services know whether an email was sent.
"""

from __future__ import annotations

from typing import Any, NoReturn

from django.contrib.auth import HASH_SESSION_KEY
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.audit.services import record as audit
from apps.core.net import client_ip
from apps.identity import errors, throttling
from apps.identity.managers import UserManager
from apps.identity.models import TokenPurpose, User
from apps.identity.services import sessions, tokens
from apps.identity.services.notifications import link, send_security_email
from apps.rbac.engine import require_perm


def _reject_token(request: HttpRequest, purpose: TokenPurpose, exc: tokens.TokenError) -> NoReturn:
    audit(
        "identity.token.rejected",
        request=request,
        outcome="failure",
        metadata={"purpose": purpose.value, "reason": exc.reason},
    )
    raise errors.InvalidToken() from exc


def _set_password(user: User, password: str) -> None:
    try:
        validate_password(password, user)
    except ValidationError as exc:
        raise ValidationError({"password": exc.messages}) from exc
    user.set_password(password)
    user.last_password_change_at = timezone.now()


# ------------------------------------------------------------------ creation and activation
@transaction.atomic
def create_user(
    *,
    actor: User | None,
    email: str,
    display_name: str = "",
    locale: str = "en",
    request: HttpRequest | None = None,
    source: str = "platform_console",
) -> User:
    """Create an unactivated account (unusable password) and send the activation email."""
    if actor is not None:
        require_perm(actor, "identity.user.create", use_cache=False)
    normalised = UserManager.normalize_email_address(email)
    if User.objects.filter(email__iexact=normalised).exists():
        raise ValidationError({"email": "An account with this email address already exists."})
    try:
        user = User.objects.create_user(normalised, None, display_name=display_name, locale=locale)
    except IntegrityError as exc:
        raise ValidationError({"email": "An account with this email already exists."}) from exc
    audit(
        "identity.account.created",
        actor=actor,
        request=request,
        target_type="identity.user",
        target_id=user.pk,
        metadata={"source": source},
    )
    _send_activation(user)
    return user


def _send_activation(user: User) -> None:
    raw = tokens.issue(user, TokenPurpose.ACTIVATION)
    send_security_email(
        "activation",
        to=user.email,
        user=user,
        context={"action_url": link(user.locale, "activate", raw)},
    )


def resend_activation(*, actor: User, user: User, request: HttpRequest) -> None:
    require_perm(actor, "identity.user.create", use_cache=False)
    if user.activated_at is not None:
        raise errors.GuardRail("already_activated", "This account is already activated.")
    _send_activation(user)
    audit(
        "identity.account.activation_resent",
        actor=actor,
        request=request,
        target_type="identity.user",
        target_id=user.pk,
    )


def _email_flow_allowed(request: HttpRequest, email: str) -> bool:
    """Per-IP limit raises 429; per-email limit is silent (still 202) to avoid enumeration."""
    ip_bucket = throttling.Bucket.named("email_flow_ip")
    ip_subject = throttling.subject_key("ip", client_ip(request) or "unknown")
    if ip_bucket.hit(ip_subject) > ip_bucket.limit:
        raise errors.RateLimited(ip_bucket.retry_after(ip_subject))
    email_bucket = throttling.Bucket.named("email_flow_email")
    return email_bucket.hit(throttling.subject_key("email", email)) <= email_bucket.limit


def request_activation_resend(request: HttpRequest, email: str) -> None:
    if not _email_flow_allowed(request, email):
        return
    user = User.objects.filter(email__iexact=email.strip()).first()
    if user is not None and user.is_active and user.activated_at is None:
        _send_activation(user)
        audit(
            "identity.account.activation_resent",
            actor_user_id=user.pk,
            request=request,
            target_type="identity.user",
            target_id=user.pk,
        )


def activate(request: HttpRequest, raw_token: str, password: str) -> User:
    try:
        with transaction.atomic():
            token = tokens.consume(raw_token, TokenPurpose.ACTIVATION)
            user = token.user
            if not user.is_active or user.activated_at is not None:
                raise tokens.TokenError("account_state")
            _set_password(user, password)
            now = timezone.now()
            user.activated_at = now
            user.email_verified_at = now
            user.save()
            audit(
                "identity.account.activated",
                actor=user,
                request=request,
                target_type="identity.user",
                target_id=user.pk,
            )
    except tokens.TokenError as exc:
        _reject_token(request, TokenPurpose.ACTIVATION, exc)
    return user


# ------------------------------------------------------------------ password reset / change
def request_password_reset(request: HttpRequest, email: str) -> None:
    if not _email_flow_allowed(request, email):
        return
    user = User.objects.filter(email__iexact=email.strip()).first()
    if user is None or not user.can_sign_in:
        return
    raw = tokens.issue(user, TokenPurpose.PASSWORD_RESET)
    send_security_email(
        "password_reset",
        to=user.email,
        user=user,
        context={"action_url": link(user.locale, "reset-password", raw)},
    )
    audit(
        "identity.password.reset_requested",
        actor_user_id=user.pk,
        request=request,
        target_type="identity.user",
        target_id=user.pk,
    )


def confirm_password_reset(request: HttpRequest, raw_token: str, password: str) -> None:
    try:
        with transaction.atomic():
            token = tokens.consume(raw_token, TokenPurpose.PASSWORD_RESET)
            user = token.user
            if not user.can_sign_in:
                raise tokens.TokenError("account_state")
            _set_password(user, password)
            user.save()
            audit(
                "identity.password.reset_completed",
                actor=user,
                request=request,
                target_type="identity.user",
                target_id=user.pk,
            )
            sessions.revoke_user_sessions(user, reason="password_reset", request=request)
    except tokens.TokenError as exc:
        _reject_token(request, TokenPurpose.PASSWORD_RESET, exc)
    throttling.clear_login_failures(throttling.subject_key("email", user.email))
    send_security_email("password_reset_done", to=user.email, user=user)


def change_password(
    request: HttpRequest, user: User, *, current_password: str, new_password: str
) -> None:
    if not user.check_password(current_password):
        raise ValidationError({"current_password": "The current password is incorrect."})
    with transaction.atomic():
        _set_password(user, new_password)
        user.save()
        audit(
            "identity.password.changed",
            actor=user,
            request=request,
            target_type="identity.user",
            target_id=user.pk,
        )
        sessions.revoke_user_sessions(
            user, reason="password_changed", keep=request, actor=user, request=request
        )
    # Keep THIS session valid (Django ties sessions to the password hash) and rotate its key.
    request.session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    sessions.rotate(request)
    send_security_email("password_changed", to=user.email, user=user)


# ------------------------------------------------------------------ email change
def request_email_change(request: HttpRequest, user: User, new_email: str) -> None:
    normalised = UserManager.normalize_email_address(new_email)
    if normalised == user.email:
        raise ValidationError({"email": "This is already your email address."})
    raw = tokens.issue(user, TokenPurpose.EMAIL_CHANGE, payload={"new_email": normalised})
    # The link goes to the NEW address; the OLD address gets a notice (no link, no new address).
    send_security_email(
        "email_change_verify",
        to=normalised,
        user=user,
        context={"action_url": link(user.locale, "verify-email", raw)},
    )
    send_security_email("email_change_notice", to=user.email, user=user)
    audit(
        "identity.email.change_requested",
        actor=user,
        request=request,
        target_type="identity.user",
        target_id=user.pk,
    )


def verify_email_change(request: HttpRequest, raw_token: str) -> User:
    try:
        with transaction.atomic():
            token = tokens.consume(raw_token, TokenPurpose.EMAIL_CHANGE)
            user = token.user
            new_email = str(token.payload.get("new_email", ""))
            if not user.can_sign_in or not new_email:
                raise tokens.TokenError("account_state")
            if User.objects.filter(email__iexact=new_email).exclude(pk=user.pk).exists():
                raise tokens.TokenError("email_unavailable")
            old_email = user.email
            user.email = new_email
            user.email_verified_at = timezone.now()
            user.save(update_fields=["email", "email_verified_at", "updated_at"])
            audit(
                "identity.email.changed",
                actor=user,
                request=request,
                target_type="identity.user",
                target_id=user.pk,
            )
            keep = request if getattr(request.user, "pk", None) == user.pk else None
            sessions.revoke_user_sessions(user, reason="email_changed", keep=keep, request=request)
    except tokens.TokenError as exc:
        _reject_token(request, TokenPurpose.EMAIL_CHANGE, exc)
    send_security_email("email_changed", to=old_email, user=user)
    return user


# ------------------------------------------------------------------ profile and lifecycle
def update_profile(request: HttpRequest, user: User, changes: dict[str, Any]) -> User:
    fields = [f for f in ("display_name", "locale") if f in changes]
    for field in fields:
        setattr(user, field, changes[field])
    if fields:
        user.save(update_fields=[*fields, "updated_at"])
        audit(
            "identity.account.updated",
            actor=user,
            request=request,
            target_type="identity.user",
            target_id=user.pk,
            metadata={"fields": fields},
        )
    return user


def admin_update_user(
    *, actor: User, user: User, changes: dict[str, Any], request: HttpRequest
) -> User:
    require_perm(actor, "identity.user.update", use_cache=False)
    fields = [f for f in ("display_name", "locale") if f in changes]
    for field in fields:
        setattr(user, field, changes[field])
    if fields:
        user.save(update_fields=[*fields, "updated_at"])
        audit(
            "identity.account.updated",
            actor=actor,
            request=request,
            target_type="identity.user",
            target_id=user.pk,
            metadata={"fields": fields},
        )
    return user


@transaction.atomic
def deactivate(*, actor: User, user: User, request: HttpRequest) -> User:
    from apps.rbac.services import GuardRailViolation, assert_not_last_super_admin

    require_perm(actor, "identity.user.deactivate", use_cache=False)
    if actor.pk == user.pk:
        raise GuardRailViolation("cannot_deactivate_self", "You cannot deactivate yourself.")
    assert_not_last_super_admin(user)
    user = User.objects.select_for_update().get(pk=user.pk)
    if user.is_active:
        user.is_active = False
        user.deactivated_at = timezone.now()
        user.save(update_fields=["is_active", "deactivated_at", "updated_at"])
        audit(
            "identity.account.deactivated",
            actor=actor,
            request=request,
            target_type="identity.user",
            target_id=user.pk,
        )
        sessions.revoke_user_sessions(user, reason="deactivated", actor=actor, request=request)
    return user


@transaction.atomic
def reactivate(*, actor: User, user: User, request: HttpRequest) -> User:
    require_perm(actor, "identity.user.deactivate", use_cache=False)
    user = User.objects.select_for_update().get(pk=user.pk)
    if not user.is_active:
        user.is_active = True
        user.deactivated_at = None
        user.save(update_fields=["is_active", "deactivated_at", "updated_at"])
        audit(
            "identity.account.reactivated",
            actor=actor,
            request=request,
            target_type="identity.user",
            target_id=user.pk,
        )
    return user
