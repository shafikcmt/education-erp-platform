"""Serializers of the tenancy API (Phase 3 M8; plan §12). Read serializers expose only the
documented fields; write serializers validate shape, the services validate rules."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from rest_framework import serializers

from apps.rbac.models import Role, RoleAssignment
from apps.tenancy.models import (
    INSTITUTION_TYPES,
    Campus,
    Institution,
    Invitation,
    Membership,
    ScopeType,
    SupportSession,
    Tenant,
)
from apps.tenancy.rules import LIMIT_KEYS, SLUG_PATTERN

_LOCALE_RE = r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$"


def _locale(**kwargs: Any) -> serializers.RegexField:
    return serializers.RegexField(_LOCALE_RE, max_length=10, **kwargs)


def _locales() -> serializers.ListField:
    return serializers.ListField(child=_locale(), max_length=10, required=False)


def _i18n() -> serializers.DictField:
    return serializers.DictField(child=serializers.CharField(max_length=200), required=False)


# --------------------------------------------------------------------------- registry
class TenantRegistrySerializer(serializers.ModelSerializer[Tenant]):
    """Platform view of a tenant: registry fields only (never ``settings`` or tenant data)."""

    limits = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = (
            "id",
            "slug",
            "name",
            "status",
            "default_locale",
            "locales",
            "timezone",
            "currency",
            "country",
            "limits",
            "limits_overridden_at",
            "limits_override_reason",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_limits(self, obj: Tenant) -> dict[str, int]:
        from apps.tenancy.limits import effective_limits

        return effective_limits(obj)


class TenantRegistryPageSerializer(serializers.Serializer[None]):
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = TenantRegistrySerializer(many=True)


class FirstInstitutionSerializer(serializers.Serializer[None]):
    institution_type = serializers.ChoiceField(choices=INSTITUTION_TYPES)
    code = serializers.SlugField(max_length=32)
    name = serializers.CharField(max_length=200)
    campus_code = serializers.SlugField(max_length=32, required=False, default="main")
    campus_name = serializers.CharField(max_length=200, required=False, default="Main campus")


class ProvisionSerializer(serializers.Serializer[None]):
    slug = serializers.RegexField(SLUG_PATTERN, max_length=32)
    name = serializers.CharField(max_length=200)
    owner_email = serializers.EmailField(max_length=254)
    institution = FirstInstitutionSerializer()
    default_locale = _locale()
    locales = _locales()
    timezone = serializers.CharField(max_length=64, required=False, default="UTC")
    currency = serializers.RegexField(r"^[A-Z]{3}$", required=False, default="USD")
    country = serializers.RegexField(r"^([A-Z]{2})?$", required=False, default="", allow_blank=True)


class RegistryUpdateSerializer(serializers.Serializer[None]):
    name = serializers.CharField(max_length=200, required=False)
    default_locale = _locale(required=False)
    locales = _locales()
    timezone = serializers.CharField(max_length=64, required=False)
    currency = serializers.RegexField(r"^[A-Z]{3}$", required=False)
    country = serializers.RegexField(r"^([A-Z]{2})?$", required=False, allow_blank=True)


class RegistryReasonSerializer(serializers.Serializer[None]):
    reason = serializers.CharField(min_length=10, max_length=200)


class LimitsSerializer(RegistryReasonSerializer):
    max_institutions = serializers.IntegerField(min_value=1, max_value=10_000)
    max_campuses = serializers.IntegerField(min_value=1, max_value=10_000)

    def limits(self) -> dict[str, int]:
        return {key: self.validated_data[key] for key in LIMIT_KEYS}


class OwnerInvitationSerializer(serializers.Serializer[None]):
    email = serializers.EmailField(max_length=254)


class MembershipSummarySerializer(serializers.Serializer[Any]):
    tenant_id = serializers.UUIDField()
    slug = serializers.CharField()
    name = serializers.CharField()
    tenant_status = serializers.CharField()
    membership_status = serializers.CharField()
    sign_in_url = serializers.CharField(allow_null=True)


class SupportRequestSerializer(serializers.Serializer[None]):
    tenant = serializers.UUIDField()
    reason = serializers.CharField(min_length=10, max_length=1000)
    ticket_ref = serializers.CharField(max_length=64)
    minutes = serializers.IntegerField(min_value=15, max_value=120)


class OwnSupportSessionSerializer(serializers.Serializer[Any]):
    session_id = serializers.UUIDField()
    tenant_id = serializers.UUIDField()
    tenant_slug = serializers.CharField()
    status = serializers.CharField()
    starts_at = serializers.DateTimeField(allow_null=True)
    ends_at = serializers.DateTimeField(allow_null=True)


class SupportSessionCreatedSerializer(serializers.Serializer[None]):
    session_id = serializers.UUIDField()
    status = serializers.CharField()


# --------------------------------------------------------------------------- tenant host
class PublicTenantSerializer(serializers.Serializer[None]):
    name = serializers.CharField()
    default_locale = serializers.CharField()
    locales = serializers.ListField(child=serializers.CharField())
    branding = serializers.DictField()


class TenantProfileSerializer(serializers.ModelSerializer[Tenant]):
    support_access_requires_approval = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = (
            "id",
            "slug",
            "name",
            "status",
            "default_locale",
            "locales",
            "timezone",
            "currency",
            "country",
            "branding",
            "support_access_requires_approval",
        )
        read_only_fields = fields

    def get_support_access_requires_approval(self, obj: Tenant) -> bool:
        value = obj.settings if isinstance(obj.settings, dict) else {}
        return value.get("support_access_requires_approval", True) is not False


def _small_dict(value: dict[Any, Any]) -> None:
    if len(value) > 20:
        raise serializers.ValidationError("At most 20 entries.")


class TenantProfileUpdateSerializer(serializers.Serializer[None]):
    name = serializers.CharField(max_length=200, required=False)
    default_locale = _locale(required=False)
    locales = _locales()
    timezone = serializers.CharField(max_length=64, required=False)
    currency = serializers.RegexField(r"^[A-Z]{3}$", required=False)
    branding = serializers.DictField(
        child=serializers.CharField(max_length=200), required=False, validators=[_small_dict]
    )


class SupportApprovalSerializer(RegistryReasonSerializer):
    requires_approval = serializers.BooleanField()


class InstitutionSerializer(serializers.ModelSerializer[Institution]):
    class Meta:
        model = Institution
        fields = (
            "id",
            "code",
            "name",
            "name_i18n",
            "institution_type",
            "settings",
            "archived_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class InstitutionCreateSerializer(serializers.Serializer[None]):
    code = serializers.SlugField(max_length=32)
    name = serializers.CharField(max_length=200)
    institution_type = serializers.ChoiceField(choices=INSTITUTION_TYPES)
    name_i18n = _i18n()


class InstitutionUpdateSerializer(serializers.Serializer[None]):
    name = serializers.CharField(max_length=200, required=False)
    name_i18n = _i18n()
    settings = serializers.DictField(required=False)


class CampusSerializer(serializers.ModelSerializer[Campus]):
    institution = serializers.UUIDField(source="institution_id", read_only=True)

    class Meta:
        model = Campus
        fields = (
            "id",
            "institution",
            "code",
            "name",
            "name_i18n",
            "address",
            "timezone",
            "is_main",
            "archived_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class CampusCreateSerializer(serializers.Serializer[None]):
    code = serializers.SlugField(max_length=32)
    name = serializers.CharField(max_length=200)
    name_i18n = _i18n()
    address = serializers.DictField(child=serializers.CharField(max_length=200), required=False)
    timezone = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class CampusUpdateSerializer(serializers.Serializer[None]):
    name = serializers.CharField(max_length=200, required=False)
    name_i18n = _i18n()
    address = serializers.DictField(child=serializers.CharField(max_length=200), required=False)
    timezone = serializers.CharField(max_length=64, required=False, allow_blank=True)
    make_main = serializers.BooleanField(required=False, default=False)


class TenantAssignmentSerializer(serializers.ModelSerializer[RoleAssignment]):
    role = serializers.UUIDField(source="role_id", read_only=True)
    role_code = serializers.CharField(source="role.code", read_only=True)
    role_name = serializers.CharField(source="role.name", read_only=True)
    institution = serializers.UUIDField(source="institution_id", read_only=True, allow_null=True)
    campus = serializers.UUIDField(source="campus_id", read_only=True, allow_null=True)

    class Meta:
        model = RoleAssignment
        fields = (
            "id",
            "role",
            "role_code",
            "role_name",
            "scope_type",
            "institution",
            "campus",
            "valid_from",
            "valid_until",
            "revoked_at",
            "reason",
        )
        read_only_fields = fields


class TenantAssignmentCreateSerializer(serializers.Serializer[None]):
    role = serializers.UUIDField()
    scope_type = serializers.ChoiceField(choices=ScopeType.choices)
    institution = serializers.UUIDField(required=False, allow_null=True, default=None)
    campus = serializers.UUIDField(required=False, allow_null=True, default=None)
    valid_until = serializers.DateTimeField(required=False, allow_null=True, default=None)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class MemberSerializer(serializers.ModelSerializer[Membership]):
    user = serializers.UUIDField(source="user_id", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    display_name = serializers.CharField(source="user.display_name", read_only=True)

    class Meta:
        model = Membership
        fields = (
            "id",
            "user",
            "email",
            "display_name",
            "status",
            "joined_at",
            "suspended_at",
            "created_at",
        )
        read_only_fields = fields


class MemberUpdateSerializer(serializers.Serializer[None]):
    status = serializers.ChoiceField(choices=[("active", "Active"), ("suspended", "Suspended")])


class TenantRoleSerializer(serializers.ModelSerializer[Role]):
    permissions = serializers.SerializerMethodField()
    template_code = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = (
            "id",
            "code",
            "name",
            "name_i18n",
            "description",
            "is_system",
            "template_code",
            "permissions",
        )
        read_only_fields = fields

    def get_permissions(self, obj: Role) -> list[str]:
        from apps.rbac.tenant_roles import role_codes

        return sorted(role_codes(obj))

    def get_template_code(self, obj: Role) -> str | None:
        template = obj.template if obj.template_id else None
        return template.code if template is not None else None


class TenantRoleCloneSerializer(serializers.Serializer[None]):
    code = serializers.RegexField(r"^[a-z][a-z0-9_]{2,63}$")
    name = serializers.CharField(max_length=120)


class TenantRoleUpdateSerializer(serializers.Serializer[None]):
    name = serializers.CharField(max_length=120, required=False)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    name_i18n = serializers.DictField(child=serializers.CharField(max_length=120), required=False)
    permissions = serializers.ListField(
        child=serializers.CharField(max_length=100), max_length=500, required=False
    )


class InvitationSerializer(serializers.ModelSerializer[Invitation]):
    role = serializers.UUIDField(source="role_id", read_only=True)
    role_code = serializers.CharField(source="role.code", read_only=True)
    institution = serializers.UUIDField(source="institution_id", read_only=True, allow_null=True)
    campus = serializers.UUIDField(source="campus_id", read_only=True, allow_null=True)

    class Meta:
        model = Invitation
        fields = (
            "id",
            "email",
            "role",
            "role_code",
            "scope_type",
            "institution",
            "campus",
            "expires_at",
            "accepted_at",
            "revoked_at",
            "created_at",
        )
        read_only_fields = fields


class InvitationCreateSerializer(serializers.Serializer[None]):
    email = serializers.EmailField(max_length=254)
    role = serializers.UUIDField()
    scope_type = serializers.ChoiceField(choices=ScopeType.choices)
    institution = serializers.UUIDField(required=False, allow_null=True, default=None)
    campus = serializers.UUIDField(required=False, allow_null=True, default=None)


class InvitationAcceptSerializer(serializers.Serializer[None]):
    token = serializers.CharField(max_length=200)
    # Only without a signed-in account: the new account's details.
    password = serializers.CharField(
        max_length=256, required=False, write_only=True, trim_whitespace=False
    )
    display_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    locale = serializers.ChoiceField(choices=settings.LANGUAGES, required=False, default="en")


class InvitationAcceptedSerializer(serializers.Serializer[None]):
    membership = serializers.UUIDField()
    status = serializers.CharField()
    account_created = serializers.BooleanField()


class SupportSessionSerializer(serializers.ModelSerializer[SupportSession]):
    staff_user = serializers.UUIDField(source="staff_user_id", read_only=True)

    class Meta:
        model = SupportSession
        fields = (
            "id",
            "status",
            "staff_user",
            "reason",
            "ticket_ref",
            "access_level",
            "duration_minutes",
            "requested_at",
            "approved_by",
            "starts_at",
            "ends_at",
            "ended_at",
            "revoked_by",
        )
        read_only_fields = fields


class BannerSerializer(serializers.Serializer[None]):
    id = serializers.UUIDField()
    status = serializers.CharField()
    ticket_ref = serializers.CharField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()


class ScopePermissionsSerializer(serializers.Serializer[None]):
    scope_type = serializers.CharField()
    institution = serializers.UUIDField(allow_null=True)
    campus = serializers.UUIDField(allow_null=True)
    permissions = serializers.ListField(child=serializers.CharField())


class LimitUsageSerializer(serializers.Serializer[Any]):
    limit = serializers.IntegerField()
    used = serializers.IntegerField()


class EntitlementsSerializer(serializers.Serializer[Any]):
    """Phase 4 M5: what the UI may show. Hidden is not secure: the server enforces."""

    modules = serializers.ListField(child=serializers.CharField())
    flags = serializers.DictField(child=serializers.BooleanField())
    limits = serializers.DictField(child=LimitUsageSerializer())


class ContextSerializer(serializers.Serializer[Any]):
    tenant = TenantProfileSerializer()
    membership_status = serializers.CharField(allow_null=True)
    is_support_session = serializers.BooleanField()
    support_session_ends_at = serializers.DateTimeField(allow_null=True)
    assignments = TenantAssignmentSerializer(many=True)
    scopes = ScopePermissionsSerializer(many=True)
    support_banner = BannerSerializer(many=True)
    entitlements = EntitlementsSerializer()
    # Phase 5 (Customization Studio) fills this; until then it is always empty.
    terminology = serializers.DictField(child=serializers.CharField())
