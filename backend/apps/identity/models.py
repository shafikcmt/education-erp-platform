"""Identity: users, email-link tokens, MFA, sessions (Phase 2 plan §6, §7).

All tables here are **platform tables** (no ``tenant_id``): a person has one global account and
joins tenants through Phase 3 memberships (ADR-032). Secrets are never stored in plaintext:

* MFA secrets: AES-GCM ciphertext (ADR-031), purpose-bound;
* recovery codes and email-link tokens: SHA-256 hashes only;
* Django session keys: SHA-256 hash in ``SessionRecord``;
* IP addresses: encrypted + HMAC blind index + coarse prefix (ADR-036).
"""

from typing import ClassVar

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models.functions import Lower

from apps.core.models import BaseModel
from apps.identity.managers import UserManager


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(max_length=254, unique=True)
    display_name = models.CharField(max_length=150, blank=True, default="")
    locale = models.CharField(
        max_length=10, choices=settings.LANGUAGES, default=settings.LANGUAGE_CODE
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(
        default=False, help_text="Unused for authorization (ADR-033); Django admin is disabled."
    )
    email_verified_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    last_password_change_at = models.DateTimeField(null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    objects: ClassVar[UserManager] = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        db_table = "identity_user"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(Lower("email"), name="identity_user_email_ci_unique"),
        ]

    def __str__(self) -> str:
        return self.email

    def clean(self) -> None:
        super().clean()
        self.email = UserManager.normalize_email_address(self.email)

    @property
    def can_sign_in(self) -> bool:
        """Active **and** activated (unactivated accounts can't log in, plan §6.5)."""
        return bool(self.is_active and self.activated_at is not None)


class TokenPurpose(models.TextChoices):
    ACTIVATION = "activation", "Account activation"
    EMAIL_VERIFICATION = "email_verification", "Email verification"
    PASSWORD_RESET = "password_reset", "Password reset"
    EMAIL_CHANGE = "email_change", "Email change"


class AccountToken(BaseModel):
    """Single-use email-link token (ADR-034). Only the SHA-256 hash is stored."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="account_tokens")
    purpose = models.CharField(max_length=32, choices=TokenPurpose.choices)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "identity_accounttoken"
        indexes = [models.Index(fields=["user", "purpose"], name="identity_tok_user_purpose")]

    def __str__(self) -> str:
        return f"{self.purpose} token for {self.user_id}"


class MFAKind(models.TextChoices):
    TOTP = "totp", "Authenticator app (TOTP)"


class MFADevice(BaseModel):
    """A TOTP authenticator. Unconfirmed devices are pending enrollments (10-minute window)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="mfa_devices")
    kind = models.CharField(max_length=16, choices=MFAKind.choices, default=MFAKind.TOTP)
    secret_encrypted = models.BinaryField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    enrollment_expires_at = models.DateTimeField(null=True, blank=True)
    manual_key_revealed_at = models.DateTimeField(null=True, blank=True)
    last_used_step = models.BigIntegerField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "identity_mfadevice"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "kind"],
                condition=models.Q(confirmed_at__isnull=False),
                name="identity_mfa_one_confirmed_per_kind",
            ),
            models.UniqueConstraint(
                fields=["user", "kind"],
                condition=models.Q(confirmed_at__isnull=True),
                name="identity_mfa_one_pending_per_kind",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} for {self.user_id}"


class RecoveryCode(BaseModel):
    """One-time MFA recovery code. Only the SHA-256 hash is stored (ADR-031 condition)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recovery_codes")
    code_hash = models.CharField(max_length=64, unique=True)
    generation = models.PositiveIntegerField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "identity_recoverycode"

    def __str__(self) -> str:
        return f"recovery code for {self.user_id}"


class SessionRecord(BaseModel):
    """Per-user index of Django sessions (Django can't list sessions per user; plan §6.7)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="session_records")
    session_key_hash = models.CharField(max_length=64, unique=True)
    # Encrypted (ADR-031) so revocation can delete the Django session itself; the middleware
    # also rejects any session whose record is revoked, so revocation never depends on it.
    session_key_encrypted = models.BinaryField(null=True, blank=True)
    host = models.CharField(max_length=255)
    last_seen_at = models.DateTimeField()
    mfa_verified_at = models.DateTimeField(null=True, blank=True)
    step_up_at = models.DateTimeField(null=True, blank=True)
    user_agent_summary = models.CharField(max_length=80, blank=True, default="")
    ip_encrypted = models.BinaryField(null=True, blank=True)
    ip_index = models.CharField(max_length=64, null=True, blank=True, db_index=True)  # noqa: DJ001 - NULL = anonymised
    ip_prefix = models.CharField(max_length=64, blank=True, default="")
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoke_reason = models.CharField(max_length=40, blank=True, default="")

    class Meta:
        db_table = "identity_sessionrecord"
        indexes = [
            models.Index(fields=["user", "revoked_at"], name="identity_sess_user_active"),
        ]

    def __str__(self) -> str:
        return f"session of {self.user_id}"


class SeenDevice(BaseModel):
    """(browser/OS family, IP HMAC) fingerprints for new sign-in notices (plan §6.11)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="seen_devices")
    fingerprint_hmac = models.CharField(max_length=64)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()

    class Meta:
        db_table = "identity_seendevice"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "fingerprint_hmac"], name="identity_seen_device_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"device of {self.user_id}"
