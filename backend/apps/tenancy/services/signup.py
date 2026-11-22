"""Self-service sign-up (Phase 5 M8; ADR-060 Q3; platform operation P23).

Off unless ``TENANCY_SIGNUP_ENABLED`` is set. A prospective owner submits the organisation's
details; the platform emails a single-use verification link (only its hash is stored; the
link expires after ``TENANCY_SIGNUP_TTL_HOURS``). A verified request waits for a platform
administrator, who approves it (the tenant is provisioned through P4 with the administrator as
the actor, and the owner receives the usual invitation) or rejects it.

Abuse controls: a per-IP limit (429), a silent per-email limit, a honeypot field, identical
responses whatever the email (no enumeration) and no external CAPTCHA. There is no automatic
approval: provisioning always has an accountable human actor (plan §13.8).
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpRequest
from django.utils import timezone

from apps.audit.services import record
from apps.core import tokens
from apps.core.net import client_ip
from apps.core.tenancy.platform import platform_scope
from apps.identity import throttling
from apps.identity.errors import RateLimited
from apps.identity.services.notifications import link, send_security_email
from apps.tenancy.models import SignupRequest, SignupStatus, Tenant
from apps.tenancy.rules import InvalidSlug, validate_slug
from apps.tenancy.services import registry

if TYPE_CHECKING:
    from apps.identity.models import User

OPEN = (SignupStatus.PENDING, SignupStatus.VERIFIED)
_INVALID = "This link is invalid or has expired."


def enabled() -> bool:
    return bool(getattr(settings, "TENANCY_SIGNUP_ENABLED", False))


def _require_enabled() -> None:
    if not enabled():
        raise Http404  # indistinguishable from a route that does not exist


def _throttle(request: HttpRequest, bucket_name: str) -> None:
    bucket = throttling.Bucket.named(bucket_name)
    subject = throttling.subject_key("ip", client_ip(request) or "unknown")
    if bucket.hit(subject) > bucket.limit:
        raise RateLimited(bucket.retry_after(subject))


def request_signup(request: HttpRequest, data: dict[str, Any]) -> None:
    """Record a sign-up and send the verification email. Silent on the honeypot and on the
    per-email limit; the caller answers 202 either way."""
    _require_enabled()
    _throttle(request, "signup_ip")
    if data.get("website"):
        return  # honeypot: bots fill every field
    email = data["email"].strip().lower()
    email_bucket = throttling.Bucket.named("signup_email")
    if email_bucket.hit(throttling.subject_key("email", email)) > email_bucket.limit:
        return
    try:
        slug = validate_slug(data["slug"])
    except InvalidSlug as exc:
        raise ValidationError({"slug": exc.messages[0]}) from None
    try:
        ZoneInfo(data["timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        raise ValidationError({"timezone": "Unknown time zone."}) from None
    if Tenant.objects.filter(slug=slug).exists():  # subdomains are public anyway
        raise ValidationError({"slug": "This name is not available."})
    raw, digest = tokens.generate_token()
    with platform_scope(operation="P23", actor=request.user, reason="self-service sign-up"):
        row = SignupRequest.objects.create(
            email=email,
            organisation_name=data["organisation_name"].strip(),
            slug=slug,
            institution_type=data["institution_type"],
            institution_name=data["institution_name"].strip(),
            default_locale=data["default_locale"],
            timezone=data["timezone"],
            currency=data["currency"],
            country=data.get("country", ""),
            token_hash=digest,
            expires_at=timezone.now() + timedelta(hours=settings.TENANCY_SIGNUP_TTL_HOURS),
        )
        record(
            "tenancy.signup.requested",
            request=request,
            target_type="tenancy.signup",
            target_id=row.pk,
            metadata={"slug": slug, "institution_type": row.institution_type},
        )
    send_security_email(
        "signup_verify",
        to=email,
        user=None,
        locale=row.default_locale,
        context={
            "organisation": row.organisation_name,
            "verify_url": link(row.default_locale, "signup/verify", raw),
            "hours": settings.TENANCY_SIGNUP_TTL_HOURS,
        },
    )


def verify_signup(request: HttpRequest, raw_token: str) -> None:
    _require_enabled()
    _throttle(request, "signup_verify_ip")
    now = timezone.now()
    with platform_scope(operation="P23", actor=request.user, reason="sign-up verification"):
        updated = SignupRequest.objects.filter(
            token_hash=tokens.hash_token(raw_token or ""),
            status=SignupStatus.PENDING,
            expires_at__gt=now,
        ).update(status=SignupStatus.VERIFIED, verified_at=now, updated_at=now)
        if not updated:
            raise ValidationError({"token": _INVALID})
        row = SignupRequest.objects.get(token_hash=tokens.hash_token(raw_token))
        record(
            "tenancy.signup.verified",
            request=request,
            target_type="tenancy.signup",
            target_id=row.pk,
            metadata={"slug": row.slug},
        )


def expire_stale(now: Any = None) -> int:
    """Mark unverified requests past their expiry (also run on every listing)."""
    now = now or timezone.now()
    return SignupRequest.objects.filter(status=SignupStatus.PENDING, expires_at__lte=now).update(
        status=SignupStatus.EXPIRED, updated_at=now
    )


def approve_signup(*, actor: User, signup_id: Any, request: HttpRequest | None = None) -> Tenant:
    """Provision the tenant (P4, with this administrator as the actor). A request is approved at
    most once: the conditional update claims it, so concurrent approvals cannot both proceed."""
    now = timezone.now()
    claimed = SignupRequest.objects.filter(pk=signup_id, status=SignupStatus.VERIFIED).update(
        status=SignupStatus.PROVISIONING, updated_at=now
    )
    if not claimed:
        raise ValidationError({"status": "Only verified requests can be approved."})
    row = SignupRequest.objects.get(pk=signup_id)
    locales = [row.default_locale] + [c for c in ("en", "bn") if c != row.default_locale]
    try:
        tenant = registry.provision_tenant(
            actor=actor,
            slug=row.slug,
            name=row.organisation_name,
            owner_email=row.email,
            institution=registry.FirstInstitution(
                institution_type=row.institution_type, code="main", name=row.institution_name
            ),
            default_locale=row.default_locale,
            locales=locales,
            timezone_name=row.timezone,
            currency=row.currency,
            country=row.country,
            request=request,
        )
    except BaseException:
        SignupRequest.objects.filter(pk=row.pk, status=SignupStatus.PROVISIONING).update(
            status=SignupStatus.VERIFIED, updated_at=timezone.now()
        )
        raise
    SignupRequest.objects.filter(pk=row.pk).update(
        status=SignupStatus.APPROVED,
        decided_at=timezone.now(),
        decided_by=actor,
        provisioned_tenant=tenant,
        updated_at=timezone.now(),
    )
    record(
        "tenancy.signup.approved",
        actor=actor,
        request=request,
        target_type="tenancy.signup",
        target_id=row.pk,
        metadata={"slug": row.slug, "tenant_id": str(tenant.pk)},
    )
    return tenant


def reject_signup(
    *, actor: User, signup_id: Any, reason: str, request: HttpRequest | None = None
) -> SignupRequest:
    cleaned = (reason or "").strip()
    if not 10 <= len(cleaned) <= 200:
        raise ValidationError({"reason": "Explain the reason in 10 to 200 characters."})
    with transaction.atomic():
        row = SignupRequest.objects.select_for_update().filter(pk=signup_id).first()
        if row is None or row.status not in OPEN:
            raise ValidationError({"status": "Only open requests can be rejected."})
        row.status = SignupStatus.REJECTED
        row.decided_at = timezone.now()
        row.decided_by = actor
        row.decision_reason = cleaned
        row.save()
    record(
        "tenancy.signup.rejected",
        actor=actor,
        request=request,
        target_type="tenancy.signup",
        target_id=row.pk,
        metadata={"slug": row.slug},
    )
    return row


def purge_closed(now: Any = None) -> int:
    """Data minimisation: delete requests older than the retention period, except those still
    waiting for a decision (an administrator must decide or reject them first)."""
    now = now or timezone.now()
    expire_stale(now)
    cutoff = now - timedelta(days=settings.TENANCY_SIGNUP_RETENTION_DAYS)
    deleted, _ = (
        SignupRequest.objects.filter(created_at__lt=cutoff)
        .exclude(status__in=(SignupStatus.VERIFIED, SignupStatus.PROVISIONING))
        .delete()
    )
    return deleted
