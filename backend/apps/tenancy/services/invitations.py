"""Tenant invitations (Phase 3 M4; plan §4.1, §13.2; ADR-034 tokens).

* Only the SHA-256 hash of the token is stored; the raw token exists only in the email link
  (URL fragment) and in the request that redeems it.
* Inviting needs ``tenancy.member.invite`` in the scope of the offered role, and the inviter
  must hold every permission of that role there.
* Accepting: the token identifies the invitation only. The signed-in account's **verified**
  email must equal the invited email. Unknown, expired, used and revoked tokens are answered
  identically (``invitation_invalid``), and each failed attempt leaves durable evidence.
* Accepting creates (or re-activates) the membership and the offered assignment in one
  transaction.
* Without a session (M8): :func:`accept_without_session` creates the account (active, email
  verified: the token proves control of the address) or checks the existing account's
  password, then accepts in the same transaction.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.services import record
from apps.core.tokens import generate_token, hash_token
from apps.identity import throttling
from apps.identity.services.notifications import send_security_email
from apps.rbac.engine import bump_tenant_version, require_perm
from apps.rbac.services import GuardRailViolation
from apps.tenancy.errors import (
    InvitationEmailMismatch,
    InvitationInvalid,
    InvitationRateLimited,
)
from apps.tenancy.models import Invitation, Membership, TenantDomain
from apps.tenancy.services import common
from apps.tenancy.services.assignments import create_assignment

if TYPE_CHECKING:
    from django.http import HttpRequest

    from apps.identity.models import User

INVITE = "tenancy.member.invite"
LIFETIME = timedelta(days=7)


def invitation_link(locale: str, token: str) -> str:
    """Link on the tenant's own host; the token travels in the URL fragment only."""
    return tenant_link(locale, "accept-invitation", token)


def tenant_link(locale: str, page: str, token: str) -> str:
    """A frontend link on the current tenant's own host (primary verified domain); the token
    travels in the URL fragment only (never sent to servers or in Referer)."""
    base = urlsplit(settings.FRONTEND_BASE_URL)
    domain = (
        TenantDomain.objects.filter(is_primary=True, verified_at__isnull=False)
        .values_list("domain", flat=True)
        .first()
    )
    host = domain or base.hostname or ""
    port = f":{base.port}" if base.port else ""
    return f"{base.scheme}://{host}{port}/{locale}/{page}#token={token}"


def _throttle(ctx_id: Any, email: str) -> None:
    for name, subject in (
        ("invite_tenant", f"t:{ctx_id}"),
        ("invite_email", throttling.subject_key("invite", f"t:{ctx_id}:{email}")),
    ):
        bucket = throttling.Bucket.named(name)
        if bucket.hit(subject) > bucket.limit:
            raise InvitationRateLimited(extra={"retry_after": bucket.retry_after(subject)})


def _send(invitation: Invitation, raw_token: str, tenant_name: str) -> None:
    # The link is built now, inside the tenant transaction; the email leaves only after the
    # invitation is committed, so a rolled-back request sends nothing.
    link = invitation_link(settings.LANGUAGE_CODE, raw_token)
    to = invitation.email

    def deliver() -> None:
        send_security_email(
            "tenant_invitation",
            to=to,
            user=None,
            context={"tenant_name": tenant_name, "action_url": link},
        )

    transaction.on_commit(deliver)


@transaction.atomic
def create_invitation(
    *,
    actor: User,
    email: str,
    role: Any,
    scope_type: str,
    institution: Any = None,
    campus: Any = None,
    request: HttpRequest | None = None,
) -> tuple[Invitation, str]:
    """Create an invitation and queue its email. Returns ``(invitation, raw_token)``; the raw
    token is never stored or logged."""
    ctx = common.tenant_context()
    target, inst, camp = common.resolve_scope(ctx, scope_type, institution, campus)
    require_perm(actor, INVITE, target=target, use_cache=False)
    tenant_role = common.tenant_role(ctx, role)
    common.assert_no_escalation(actor, tenant_role, target)
    return issue_invitation(
        actor=actor,
        email=email,
        role=tenant_role,
        scope_type=scope_type,
        institution=inst,
        campus=camp,
        request=request,
        recheck_inviter=True,
    )


def issue_invitation(
    *,
    actor: Any,
    email: str,
    role: Any,
    scope_type: str,
    institution: Any = None,
    campus: Any = None,
    request: HttpRequest | None = None,
    recheck_inviter: bool = False,
) -> tuple[Invitation, str]:
    """Store and send an invitation WITHOUT authorising ``actor`` against the tenant. For
    callers that authorised it already: :func:`create_invitation`, and provisioning (P4),
    where a platform operator invites the first owner."""
    ctx = common.tenant_context()
    tenant_role = common.tenant_role(ctx, role)
    inst, camp = institution, campus
    address = email.strip().lower()
    if not address or "@" not in address or len(address) > 254:
        raise ValidationError({"email": "Enter a valid email address."})
    _throttle(ctx.id, address)
    raw, token_hash = generate_token()
    tenant = common.lock_tenant(ctx)
    try:
        with transaction.atomic():
            invitation = Invitation.objects.create(
                email=address,
                role=tenant_role,
                scope_type=scope_type,
                institution=inst,
                campus=camp,
                token_hash=token_hash,
                expires_at=timezone.now() + LIFETIME,
                invited_by=getattr(actor, "pk", None),
                recheck_inviter=recheck_inviter,
            )
    except IntegrityError:
        raise ValidationError(
            {"email": "An open invitation for this role and scope already exists."}
        ) from None
    record(
        "tenancy.invitation.created",
        actor=actor,
        request=request,
        target_type="tenancy.invitation",
        target_id=invitation.pk,
        metadata={"role_code": tenant_role.code, "scope_type": scope_type},
    )
    _send(invitation, raw, tenant.name)
    return invitation, raw


@transaction.atomic
def revoke_invitation(
    *, actor: User, invitation: Invitation, request: HttpRequest | None = None
) -> Invitation:
    ctx = common.tenant_context()
    invitation = Invitation.objects.select_related("role").get(pk=invitation.pk)
    target, _, _ = common.resolve_scope(
        ctx, invitation.scope_type, invitation.institution_id, invitation.campus_id
    )
    require_perm(actor, INVITE, target=target, use_cache=False)
    if invitation.accepted_at is None and invitation.revoked_at is None:
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at", "updated_at"])
        record(
            "tenancy.invitation.revoked",
            actor=actor,
            request=request,
            target_type="tenancy.invitation",
            target_id=invitation.pk,
        )
    return invitation


@transaction.atomic
def resend_invitation(
    *, actor: User, invitation: Invitation, request: HttpRequest | None = None
) -> tuple[Invitation, str]:
    """Issue a fresh token (the old link stops working) and send it again."""
    ctx = common.tenant_context()
    invitation = Invitation.objects.select_related("role").get(pk=invitation.pk)
    target, _, _ = common.resolve_scope(
        ctx, invitation.scope_type, invitation.institution_id, invitation.campus_id
    )
    require_perm(actor, INVITE, target=target, use_cache=False)
    common.assert_no_escalation(actor, invitation.role, target)
    if invitation.accepted_at is not None or invitation.revoked_at is not None:
        raise InvitationInvalid()
    _throttle(ctx.id, invitation.email)
    raw, invitation.token_hash = generate_token()
    invitation.expires_at = timezone.now() + LIFETIME
    invitation.save(update_fields=["token_hash", "expires_at", "updated_at"])
    record(
        "tenancy.invitation.resent",
        actor=actor,
        request=request,
        target_type="tenancy.invitation",
        target_id=invitation.pk,
    )
    _send(invitation, raw, common.lock_tenant(ctx).name)
    return invitation, raw


def _record_attempt(reason: str, request: HttpRequest | None, user: Any) -> None:
    record(
        "tenancy.invitation.invalid_attempt",
        outcome="denied",
        actor=user,
        request=request,
        metadata={"reason": reason},
        durable=True,
    )


def _reject(reason: str, request: HttpRequest | None, user: Any) -> InvitationInvalid:
    _record_attempt(reason, request, user)
    return InvitationInvalid()


def _inviter_still_authorised(ctx: Any, invitation: Invitation) -> bool:
    """ADR-062: the member who invited must still be an active member who may invite into this
    scope and holds every permission of the role (uncached). Otherwise the invitation is void,
    so removing someone's rights also stops the invitations they sent."""
    from apps.identity.models import User

    if not invitation.recheck_inviter:
        return True
    if invitation.invited_by is None:
        return False  # a member invitation always names its inviter
    inviter = User.objects.filter(pk=invitation.invited_by, is_active=True).first()
    member = Membership.objects.filter(user_id=invitation.invited_by).first()
    if inviter is None or member is None or member.status != Membership.Status.ACTIVE:
        return False
    try:
        target, _, _ = common.resolve_scope(
            ctx, invitation.scope_type, invitation.institution, invitation.campus
        )
        require_perm(inviter, INVITE, target=target, use_cache=False)
        common.assert_no_escalation(inviter, invitation.role, target)
    except (PermissionDenied, GuardRailViolation, ValidationError):
        return False
    return True


def accept_invitation(*, token: str, user: User, request: HttpRequest | None = None) -> Membership:
    """Redeem ``token`` for the signed-in ``user`` inside the current tenant."""
    ctx = common.tenant_context()
    invitation = (
        Invitation.objects.select_for_update().filter(token_hash=hash_token(token or "")).first()
    )
    if invitation is None:
        raise _reject("unknown", request, user)
    mine = (user.email or "").strip().lower() == invitation.email and bool(
        getattr(user, "email_verified_at", None)
    )
    if invitation.revoked_at is not None:
        raise _reject("revoked", request, user)
    if invitation.accepted_at is not None:
        # Idempotent for the same person; indistinguishable from "used" for anyone else.
        existing = Membership.objects.filter(user_id=user.pk).first() if mine else None
        if existing is None:
            raise _reject("used", request, user)
        return existing
    if invitation.expires_at <= timezone.now():
        raise _reject("expired", request, user)
    if not _inviter_still_authorised(ctx, invitation):
        raise _reject("inviter_unauthorised", request, user)
    if not mine:
        record(
            "tenancy.invitation.invalid_attempt",
            outcome="denied",
            actor=user,
            request=request,
            metadata={"reason": "email_mismatch"},
            durable=True,
        )
        raise InvitationEmailMismatch()
    with transaction.atomic():
        membership = Membership.objects.select_for_update().filter(user_id=user.pk).first()
        if membership is None:
            membership = Membership.objects.create(
                user=user,
                status=Membership.Status.ACTIVE,
                invited_by=invitation.invited_by,
                joined_at=timezone.now(),
            )
        elif membership.status == Membership.Status.SUSPENDED:
            # A suspension is lifted by an administrator, never by an old invitation.
            raise _reject("membership_suspended", request, user)
        elif membership.status != Membership.Status.ACTIVE:
            membership.status = Membership.Status.ACTIVE
            membership.joined_at = membership.joined_at or timezone.now()
            membership.save(update_fields=["status", "joined_at", "updated_at"])
        create_assignment(
            membership=membership,
            role=invitation.role,
            scope_type=invitation.scope_type,
            institution=invitation.institution,
            campus=invitation.campus,
            granted_by=invitation.invited_by,
            reason="invitation",
        )
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["accepted_at", "updated_at"])
        bump_tenant_version(ctx.id)
        record(
            "tenancy.invitation.accepted",
            actor=user,
            request=request,
            target_type="tenancy.invitation",
            target_id=invitation.pk,
            metadata={"role_code": invitation.role.code, "scope_type": invitation.scope_type},
        )
    return membership


def accept_without_session(
    *,
    token: str,
    password: str,
    display_name: str = "",
    locale: str = "en",
    request: HttpRequest | None = None,
) -> tuple[Membership, User, bool]:
    """Redeem ``token`` on the tenant host without a session (Phase 3 M8).

    A non-member can't sign in on a tenant host (D7), so the invitation is redeemed with the
    password instead:

    * no account for the invited address: one is created, active and with a verified email
      (the token proves control of the address), in the same transaction as the membership;
    * an account exists: its password must match. Failures get the generic
      ``invalid_credentials`` answer, are throttled per invitation and leave durable evidence.

    Returns ``(membership, user, account_created)``."""
    from apps.identity import errors as identity_errors
    from apps.identity.models import User
    from apps.identity.services.accounts import create_invited_account

    common.tenant_context()
    invitation = Invitation.objects.filter(token_hash=hash_token(token or "")).first()
    reason = (
        "unknown"
        if invitation is None
        else "revoked"
        if invitation.revoked_at is not None
        else "used"
        if invitation.accepted_at is not None
        else "expired"
        if invitation.expires_at <= timezone.now()
        else ""
    )
    if reason:
        raise _reject(reason, request, None)
    assert invitation is not None  # noqa: S101 - narrowed above
    existing = User.objects.filter(email__iexact=invitation.email).first()
    if existing is None:
        with transaction.atomic():
            user = create_invited_account(
                email=invitation.email,
                password=password,
                display_name=display_name,
                locale=locale,
                request=request,
            )
            membership = accept_invitation(token=token, user=user, request=request)
        return membership, user, True
    bucket = throttling.Bucket.named("invite_accept")
    subject = f"invitation:{invitation.pk}"
    if bucket.count(subject) >= bucket.limit:
        raise identity_errors.RateLimited(bucket.retry_after(subject))
    usable = existing.is_active and existing.activated_at is not None
    if not (usable and existing.check_password(password)):
        bucket.hit(subject)
        _record_attempt("bad_credentials", request, existing)
        raise identity_errors.InvalidCredentials()
    return accept_invitation(token=token, user=existing, request=request), existing, False
