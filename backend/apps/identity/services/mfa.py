"""TOTP MFA, recovery codes and the one-time manual key (plan §6.6; ADR-031, ADR-038).

* RFC 6238: 30 s steps, 6 digits, ±1 step; the last accepted step is stored to block replay.
* Secrets are AES-GCM encrypted, bound to the device id (purpose string).
* Setup returns only a server-rendered SVG QR (no ``otpauth://`` URI, no secret field).
* Manual key (ADR-038): unconfirmed device, inside its enrollment window, after a fresh step-up,
  **once**; afterwards ``410``. Restarting setup creates a new secret.
* Recovery codes: 10 x 16 base32 characters (80 bits); only SHA-256 hashes are stored.
"""

from __future__ import annotations

import base64
import os
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

import pyotp
import segno
from django.conf import settings
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone
from django.utils.crypto import constant_time_compare

from apps.audit.services import record as audit
from apps.core import crypto
from apps.core.tokens import hash_token
from apps.identity import errors
from apps.identity import session_state as state
from apps.identity.models import MFADevice, MFAKind, RecoveryCode
from apps.identity.services import sessions
from apps.identity.services.notifications import send_security_email
from apps.identity.throttling import Bucket, subject_key

if TYPE_CHECKING:
    from apps.identity.models import User

RECOVERY_CODE_COUNT = 10
_DIGITS = 6
_INTERVAL = 30


def _purpose(device_id: uuid.UUID | str) -> str:
    return f"identity.mfadevice.secret:{device_id}"


def device_secret(device: MFADevice) -> str:
    return crypto.decrypt_str(device.secret_encrypted, purpose=_purpose(device.pk))


def confirmed_device(user: User) -> MFADevice | None:
    return MFADevice.objects.filter(
        user=user, kind=MFAKind.TOTP, confirmed_at__isnull=False
    ).first()


def has_mfa(user: User) -> bool:
    return confirmed_device(user) is not None


def _matching_step(secret: str, code: str, last_used_step: int | None) -> int | None:
    code = "".join(code.split())
    if len(code) != _DIGITS or not code.isdigit():
        return None
    totp = pyotp.TOTP(secret, digits=_DIGITS, interval=_INTERVAL)
    current = totp.timecode(timezone.now())
    for step in (current - 1, current, current + 1):
        if last_used_step is not None and step <= last_used_step:
            continue  # replay of an already-used (or older) step
        if constant_time_compare(totp.generate_otp(step), code):
            return step
    return None


def verify_totp(device: MFADevice, code: str) -> bool:
    """Verify and consume a code (row-locked, so a code can't be used twice concurrently)."""
    with transaction.atomic():
        locked = MFADevice.objects.select_for_update().get(pk=device.pk)
        step = _matching_step(device_secret(locked), code, locked.last_used_step)
        if step is None:
            return False
        locked.last_used_step = step
        locked.last_used_at = timezone.now()
        locked.save(update_fields=["last_used_step", "last_used_at", "updated_at"])
        return True


def _normalise_recovery(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def use_recovery_code(user: User, code: str) -> int | None:
    """Consume a recovery code; return the number remaining, or ``None`` if invalid."""
    normalised = _normalise_recovery(code)
    if len(normalised) != 16:
        return None
    with transaction.atomic():
        row = (
            RecoveryCode.objects.select_for_update()
            .filter(user=user, code_hash=hash_token(normalised), used_at__isnull=True)
            .first()
        )
        if row is None:
            return None
        row.used_at = timezone.now()
        row.save(update_fields=["used_at", "updated_at"])
        return RecoveryCode.objects.filter(user=user, used_at__isnull=True).count()


def _new_recovery_codes(user: User) -> list[str]:
    generation = (
        RecoveryCode.objects.filter(user=user)
        .order_by("-generation")
        .values_list("generation", flat=True)
        .first()
        or 0
    ) + 1
    RecoveryCode.objects.filter(user=user).delete()
    codes = [base64.b32encode(os.urandom(10)).decode() for _ in range(RECOVERY_CODE_COUNT)]
    RecoveryCode.objects.bulk_create(
        [RecoveryCode(user=user, code_hash=hash_token(c), generation=generation) for c in codes]
    )
    return ["-".join(c[i : i + 4] for i in range(0, 16, 4)) for c in codes]


# ------------------------------------------------------------------ enrollment
@dataclass(frozen=True)
class Enrollment:
    device: MFADevice
    qr_svg_data_uri: str


def _pending(user: User, device_id: uuid.UUID | str) -> MFADevice:
    device = (
        MFADevice.objects.select_for_update()
        .filter(pk=device_id, user=user, confirmed_at__isnull=True)
        .first()
    )
    if device is None or (
        device.enrollment_expires_at is not None and device.enrollment_expires_at < timezone.now()
    ):
        raise errors.EnrollmentNotFound()
    return device


@transaction.atomic
def start_enrollment(user: User, *, request: HttpRequest) -> Enrollment:
    if has_mfa(user):
        raise errors.GuardRail("mfa_already_enrolled", "Two-factor authentication is already on.")
    MFADevice.objects.filter(user=user, confirmed_at__isnull=True).delete()  # restart = new secret
    device = MFADevice(
        user=user,
        kind=MFAKind.TOTP,
        enrollment_expires_at=timezone.now()
        + timedelta(seconds=settings.MFA_ENROLLMENT_TTL_SECONDS),
    )
    secret = pyotp.random_base32()
    device.secret_encrypted = crypto.encrypt_str(secret, purpose=_purpose(device.pk))
    device.save()
    uri = pyotp.TOTP(secret, digits=_DIGITS, interval=_INTERVAL).provisioning_uri(
        name=user.email, issuer_name=settings.MFA_ISSUER
    )
    qr = segno.make(uri, error="m").svg_data_uri(scale=5, border=2)
    audit(
        "identity.mfa.enrollment_started",
        actor=user,
        request=request,
        target_type="identity.mfadevice",
        target_id=device.pk,
        metadata={"device_id": str(device.pk)},
    )
    return Enrollment(device=device, qr_svg_data_uri=qr)


def reveal_manual_key(user: User, device_id: uuid.UUID | str, *, request: HttpRequest) -> str:
    """ADR-038: return the base32 key **once**, grouped in fours, after a fresh step-up."""
    bucket = Bucket.named("step_up")
    subject = subject_key("manual_key", str(user.pk))
    if Bucket("manual_key", bucket.limit, bucket.window).hit(subject) > bucket.limit:
        raise errors.RateLimited(bucket.retry_after(subject))
    if not state.step_up_fresh(request):
        raise errors.StepUpRequired()
    with transaction.atomic():
        device = _pending(user, device_id)
        already_shown = device.manual_key_revealed_at is not None
        if not already_shown:
            device.manual_key_revealed_at = timezone.now()
            device.save(update_fields=["manual_key_revealed_at", "updated_at"])
            audit(
                "identity.mfa.manual_key_revealed",
                actor=user,
                request=request,
                target_type="identity.mfadevice",
                target_id=device.pk,
                metadata={"device_id": str(device.pk)},
            )
            secret = device_secret(device)
    if already_shown:
        # Outside the transaction, so the denied attempt stays in the audit log.
        audit(
            "identity.mfa.manual_key_revealed",
            actor=user,
            request=request,
            outcome="denied",
            target_type="identity.mfadevice",
            target_id=device.pk,
            metadata={"device_id": str(device.pk), "reason": "already_shown"},
        )
        raise errors.ManualKeyAlreadyShown()
    return " ".join(secret[i : i + 4] for i in range(0, len(secret), 4))


@transaction.atomic
def cancel_enrollment(user: User, device_id: uuid.UUID | str, *, request: HttpRequest) -> None:
    device = _pending(user, device_id)
    device_pk = device.pk
    device.delete()  # destroys the pending secret
    audit(
        "identity.mfa.enrollment_cancelled",
        actor=user,
        request=request,
        target_type="identity.mfadevice",
        target_id=device_pk,
        metadata={"device_id": str(device_pk)},
    )


def confirm_enrollment(
    user: User, device_id: uuid.UUID | str, code: str, *, request: HttpRequest
) -> list[str]:
    """Activate the device with a valid code; return the recovery codes (shown once)."""
    with transaction.atomic():
        device = _pending(user, device_id)
        step = _matching_step(device_secret(device), code, None)
        if step is None:
            audit(
                "identity.mfa.challenge_failed",
                actor=user,
                request=request,
                outcome="failure",
                metadata={"reason": "enrollment_code"},
            )
            raise errors.InvalidMfaCode()
        now = timezone.now()
        device.confirmed_at = now
        device.enrollment_expires_at = None
        device.last_used_step = step
        device.last_used_at = now
        device.save()
        codes = _new_recovery_codes(user)
        audit(
            "identity.mfa.enrolled",
            actor=user,
            request=request,
            target_type="identity.mfadevice",
            target_id=device.pk,
            metadata={"device_id": str(device.pk)},
        )
    sessions.mark_mfa_verified(request)
    return codes


@transaction.atomic
def regenerate_recovery_codes(user: User, *, request: HttpRequest) -> list[str]:
    if not has_mfa(user):
        raise errors.GuardRail("mfa_not_enrolled", "Two-factor authentication is not set up.")
    codes = _new_recovery_codes(user)
    audit(
        "identity.mfa.recovery_codes_regenerated",
        actor=user,
        request=request,
        metadata={"count": len(codes)},
    )
    return codes


def disable_mfa(user: User, *, request: HttpRequest, required: bool) -> None:
    if required:
        raise errors.MfaRequiredForAccount()
    with transaction.atomic():
        MFADevice.objects.filter(user=user).delete()
        RecoveryCode.objects.filter(user=user).delete()
        audit(
            "identity.mfa.disabled",
            actor=user,
            request=request,
            target_type="identity.user",
            target_id=user.pk,
        )
        sessions.revoke_user_sessions(
            user, reason="mfa_disabled", keep=request, actor=user, request=request
        )
    request.session.pop(state.MFA_VERIFIED_AT, None)
    send_security_email("mfa_disabled", to=user.email, user=user)


def admin_reset_mfa(actor: User, user: User, *, reason: str, request: HttpRequest) -> None:
    """``identity.mfa.reset`` + step-up + reason (checked by the API and here)."""
    from apps.rbac.engine import require_perm

    require_perm(actor, "identity.mfa.reset", use_cache=False)
    with transaction.atomic():
        MFADevice.objects.filter(user=user).delete()
        RecoveryCode.objects.filter(user=user).delete()
        audit(
            "identity.mfa.reset",
            actor=actor,
            request=request,
            target_type="identity.user",
            target_id=user.pk,
            metadata={"reason": reason.strip()[:200]},
        )
        sessions.revoke_user_sessions(user, reason="mfa_reset", actor=actor, request=request)
    send_security_email("mfa_reset", to=user.email, user=user)
