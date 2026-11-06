"""``AccountToken`` issue/consume (ADR-034): random, hashed, single-use, expiring, purpose-bound;
a new token invalidates older unused ones of the same purpose."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.tokens import generate_token, hash_token
from apps.identity.models import AccountToken, TokenPurpose, User

LIFETIMES = {
    TokenPurpose.ACTIVATION: timedelta(hours=72),
    TokenPurpose.EMAIL_VERIFICATION: timedelta(hours=24),
    TokenPurpose.PASSWORD_RESET: timedelta(minutes=30),
    TokenPurpose.EMAIL_CHANGE: timedelta(hours=24),
}


class TokenError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@transaction.atomic
def issue(user: User, purpose: TokenPurpose, payload: dict[str, Any] | None = None) -> str:
    now = timezone.now()
    AccountToken.objects.filter(
        user=user, purpose=purpose, used_at__isnull=True, invalidated_at__isnull=True
    ).update(invalidated_at=now)
    raw, token_hash = generate_token()
    AccountToken.objects.create(
        user=user,
        purpose=purpose,
        token_hash=token_hash,
        expires_at=now + LIFETIMES[purpose],
        payload=payload or {},
    )
    return raw


def invalidate_all(user: User, *, reason: str, request: Any = None, actor: Any = None) -> int:
    """Invalidate every unused email-link token of ``user`` (review M2): called after password
    change/reset, email change, MFA reset and deactivation, so older links can't be replayed."""
    from apps.audit.services import record as audit

    count = AccountToken.objects.filter(
        user=user, used_at__isnull=True, invalidated_at__isnull=True
    ).update(invalidated_at=timezone.now())
    if count:
        audit(
            "identity.token.invalidated",
            actor=actor,
            actor_user_id=None if actor else user.pk,
            request=request,
            target_type="identity.user",
            target_id=user.pk,
            metadata={"reason": reason, "count": count},
        )
    return int(count)


def consume(raw: str, purpose: TokenPurpose) -> AccountToken:
    """Validate and mark the token used. Must run inside the caller's transaction."""
    token = (
        AccountToken.objects.select_for_update()
        .select_related("user")
        .filter(token_hash=hash_token(raw.strip()))
        .first()
    )
    if token is None:
        raise TokenError("unknown")
    if token.purpose != purpose:
        raise TokenError("wrong_purpose")
    if token.used_at is not None:
        raise TokenError("used")
    if token.invalidated_at is not None:
        raise TokenError("superseded")
    if token.expires_at <= timezone.now():
        raise TokenError("expired")
    token.used_at = timezone.now()
    token.save(update_fields=["used_at", "updated_at"])
    return token
