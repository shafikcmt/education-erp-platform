"""Request/response serializers. Secret-bearing fields are write-only, and one-time secrets
(QR, manual key, recovery codes) appear only in their single response."""

from typing import Any

from django.conf import settings
from rest_framework import serializers

from apps.core.net import mask_prefix
from apps.identity.models import SessionRecord, User


def _password() -> serializers.CharField:
    return serializers.CharField(max_length=4096, trim_whitespace=False, write_only=True)


def _token() -> serializers.CharField:
    return serializers.CharField(max_length=256, write_only=True)


LOCALES = settings.LANGUAGES


# ------------------------------------------------------------------ auth
class LoginSerializer(serializers.Serializer[None]):
    email = serializers.CharField(max_length=254)
    password = _password()


class LoginResultSerializer(serializers.Serializer[None]):
    status = serializers.ChoiceField(
        choices=["authenticated", "mfa_required", "mfa_enrollment_required"]
    )


class MfaVerifySerializer(serializers.Serializer[None]):
    code = serializers.CharField(max_length=12, required=False, allow_blank=True, write_only=True)
    recovery_code = serializers.CharField(
        max_length=32, required=False, allow_blank=True, write_only=True
    )

    def validate(self, attrs: dict[str, str]) -> dict[str, str]:
        if bool(attrs.get("code")) == bool(attrs.get("recovery_code")):
            raise serializers.ValidationError("Provide either a code or a recovery code.")
        return attrs


class StepUpSerializer(serializers.Serializer[None]):
    password = _password()
    code = serializers.CharField(max_length=12, required=False, allow_blank=True, write_only=True)
    recovery_code = serializers.CharField(
        max_length=32, required=False, allow_blank=True, write_only=True
    )

    def validate(self, attrs: dict[str, str]) -> dict[str, str]:
        if attrs.get("code") and attrs.get("recovery_code"):
            raise serializers.ValidationError("Provide a code or a recovery code, not both.")
        return attrs


class StepUpResultSerializer(serializers.Serializer[None]):
    step_up_expires_at = serializers.IntegerField()


class EmailRequestSerializer(serializers.Serializer[None]):
    email = serializers.CharField(max_length=254)


class TokenPasswordSerializer(serializers.Serializer[None]):
    token = _token()
    password = _password()


class TokenSerializer(serializers.Serializer[None]):
    token = _token()


class AcceptedSerializer(serializers.Serializer[None]):
    detail = serializers.CharField()


class CsrfSerializer(serializers.Serializer[None]):
    detail = serializers.CharField()


# ------------------------------------------------------------------ me
class SessionInfoSerializer(serializers.Serializer[None]):
    mfa_verified = serializers.BooleanField()
    idle_expires_at = serializers.IntegerField(allow_null=True)
    absolute_expires_at = serializers.IntegerField(allow_null=True)
    step_up_expires_at = serializers.IntegerField(allow_null=True)
    idle_timeout_seconds = serializers.IntegerField()


class MeSerializer(serializers.Serializer[dict[str, Any]]):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    display_name = serializers.CharField()
    locale = serializers.CharField()
    email_verified_at = serializers.DateTimeField(allow_null=True)
    mfa_enabled = serializers.BooleanField()
    mfa_required = serializers.BooleanField()
    mfa_enrollment_required = serializers.BooleanField()
    is_platform_staff = serializers.BooleanField()
    permissions = serializers.ListField(child=serializers.CharField())
    session = SessionInfoSerializer()


class MeUpdateSerializer(serializers.Serializer[None]):
    display_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    locale = serializers.ChoiceField(choices=LOCALES, required=False)


class PasswordChangeSerializer(serializers.Serializer[None]):
    current_password = _password()
    new_password = _password()


class EmailChangeSerializer(serializers.Serializer[None]):
    new_email = serializers.EmailField(max_length=254)


class MfaStatusSerializer(serializers.Serializer[None]):
    enabled = serializers.BooleanField()
    is_required = serializers.BooleanField()
    confirmed_at = serializers.DateTimeField(allow_null=True)
    recovery_codes_remaining = serializers.IntegerField()


class MfaSetupSerializer(serializers.Serializer[None]):
    device_id = serializers.UUIDField()
    qr_svg = serializers.CharField(help_text="data:image/svg+xml URI of the enrollment QR code")
    expires_at = serializers.DateTimeField()


class ManualKeySerializer(serializers.Serializer[None]):
    manual_key = serializers.CharField(help_text="Shown once (ADR-038); then 410.")


class MfaConfirmSerializer(serializers.Serializer[None]):
    device_id = serializers.UUIDField()
    code = serializers.CharField(max_length=12, write_only=True)


class RecoveryCodesSerializer(serializers.Serializer[None]):
    recovery_codes = serializers.ListField(child=serializers.CharField())


class MfaDisableSerializer(serializers.Serializer[None]):
    pass


class SessionSerializer(serializers.ModelSerializer[SessionRecord]):
    current = serializers.SerializerMethodField()
    ip_masked = serializers.SerializerMethodField()
    mfa_verified = serializers.SerializerMethodField()

    class Meta:
        model = SessionRecord
        fields = (
            "id",
            "host",
            "created_at",
            "last_seen_at",
            "user_agent_summary",
            "ip_masked",
            "mfa_verified",
            "current",
        )

    def get_current(self, obj: SessionRecord) -> bool:
        return str(obj.pk) == str(self.context.get("current_record_id"))

    def get_ip_masked(self, obj: SessionRecord) -> str:
        return mask_prefix(obj.ip_prefix)

    def get_mfa_verified(self, obj: SessionRecord) -> bool:
        return obj.mfa_verified_at is not None


class RevokedCountSerializer(serializers.Serializer[None]):
    revoked = serializers.IntegerField()


# ------------------------------------------------------------------ platform users
class PlatformUserSerializer(serializers.ModelSerializer[User]):
    platform_roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields: tuple[str, ...] = (
            "id",
            "email",
            "display_name",
            "locale",
            "is_active",
            "activated_at",
            "email_verified_at",
            "deactivated_at",
            "created_at",
            "platform_roles",
        )
        read_only_fields: tuple[str, ...] = fields

    def get_platform_roles(self, obj: User) -> list[str]:
        return sorted(a.role.code for a in obj.platform_roles.all())


class PlatformUserSensitiveSerializer(PlatformUserSerializer):
    """Adds MFA state and session counts: only with ``identity.user.view_sensitive``."""

    mfa_enabled = serializers.SerializerMethodField()
    active_sessions = serializers.SerializerMethodField()

    class Meta(PlatformUserSerializer.Meta):
        fields = (*PlatformUserSerializer.Meta.fields, "mfa_enabled", "active_sessions")
        read_only_fields = fields

    def get_mfa_enabled(self, obj: User) -> bool:
        return obj.mfa_devices.filter(confirmed_at__isnull=False).exists()

    def get_active_sessions(self, obj: User) -> int:
        return obj.session_records.filter(revoked_at__isnull=True).count()


class PlatformUserPageSerializer(serializers.Serializer[None]):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = PlatformUserSerializer(many=True)


class PlatformUserCreateSerializer(serializers.Serializer[None]):
    email = serializers.EmailField(max_length=254)
    display_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    locale = serializers.ChoiceField(choices=LOCALES, default="en")


class PlatformUserUpdateSerializer(serializers.Serializer[None]):
    display_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    locale = serializers.ChoiceField(choices=LOCALES, required=False)


class ReasonSerializer(serializers.Serializer[None]):
    reason = serializers.CharField(min_length=5, max_length=500)
