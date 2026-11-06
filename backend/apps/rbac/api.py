"""Roles, permission catalog and platform-role assignments (/api/v1/platform/...; plan §8).

System roles are read-only. Grants/revokes need ``rbac.platform_role.assign`` (MFA + step-up);
the services enforce the anti-escalation and last-Super-Admin guard rails.
"""

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response

from apps.identity.api.utils import CsrfProtectedView, get_or_404, service_errors
from apps.identity.models import User
from apps.rbac import services
from apps.rbac.models import Permission, PlatformRoleAssignment, Role, RoleKind
from apps.rbac.permissions import HasPermission

TAGS = ["platform-rbac"]


class PermissionSerializer(serializers.ModelSerializer[Permission]):
    class Meta:
        model = Permission
        fields = (
            "code",
            "module_code",
            "description",
            "is_sensitive",
            "requires_mfa",
            "requires_step_up",
        )
        read_only_fields = fields


class RoleSerializer(serializers.ModelSerializer[Role]):
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = (
            "id",
            "code",
            "name",
            "name_i18n",
            "description",
            "kind",
            "institution_types",
            "is_system",
            "permissions",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_permissions(self, obj: Role) -> list[str]:
        return sorted(rp.permission.code for rp in obj.role_permissions.all())


class RoleCreateSerializer(serializers.Serializer[None]):
    code = serializers.RegexField(r"^[a-z][a-z0-9_]{2,63}$")
    name = serializers.CharField(max_length=120)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    name_i18n = serializers.DictField(child=serializers.CharField(max_length=120), required=False)
    permissions = serializers.ListField(child=serializers.CharField(max_length=100), max_length=500)


class RoleUpdateSerializer(serializers.Serializer[None]):
    name = serializers.CharField(max_length=120, required=False)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    name_i18n = serializers.DictField(child=serializers.CharField(max_length=120), required=False)
    permissions = serializers.ListField(
        child=serializers.CharField(max_length=100), max_length=500, required=False
    )


class AssignmentSerializer(serializers.ModelSerializer[PlatformRoleAssignment]):
    role_code = serializers.CharField(source="role.code", read_only=True)
    granted_by = serializers.UUIDField(source="granted_by_id", read_only=True, allow_null=True)

    class Meta:
        model = PlatformRoleAssignment
        fields = ("id", "role", "role_code", "granted_by", "granted_at", "reason")
        read_only_fields = fields


class GrantSerializer(serializers.Serializer[None]):
    role = serializers.UUIDField()
    reason = serializers.CharField(min_length=5, max_length=255)


def _actor(request: Request) -> User:
    assert isinstance(request.user, User)  # noqa: S101 - permission classes guarantee it
    return request.user


def roles_queryset() -> QuerySet[Role]:
    # Platform scope: platform roles and system templates (tenant roles arrive in Phase 3).
    return Role.objects.filter(tenant_id__isnull=True).prefetch_related(
        "role_permissions__permission"
    )


class PermissionsView(CsrfProtectedView):
    permission_classes = [HasPermission("rbac.permission.view")]

    @extend_schema(
        tags=TAGS, summary="Permission catalog", responses=PermissionSerializer(many=True)
    )
    def get(self, request: Request) -> Response:
        rows = Permission.objects.filter(deprecated_at__isnull=True)
        return Response(PermissionSerializer(rows, many=True).data)


class RolesView(CsrfProtectedView):
    permission_classes = [HasPermission({"GET": "rbac.role.view", "POST": "rbac.role.create"})]

    @extend_schema(
        tags=TAGS,
        summary="Platform roles and tenant role templates",
        responses=RoleSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        return Response(RoleSerializer(roles_queryset(), many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Create a platform role (step-up)",
        request=RoleCreateSerializer,
        responses={201: RoleSerializer},
    )
    def post(self, request: Request) -> Response:
        data = RoleCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with service_errors():
            role = services.create_role(
                actor=_actor(request), request=request._request, **data.validated_data
            )
        return Response(
            RoleSerializer(get_or_404(roles_queryset(), role.pk)).data,
            status=status.HTTP_201_CREATED,
        )


class RoleDetailView(CsrfProtectedView):
    permission_classes = [
        HasPermission(
            {"GET": "rbac.role.view", "PATCH": "rbac.role.update", "DELETE": "rbac.role.delete"}
        )
    ]

    @extend_schema(tags=TAGS, summary="Role detail", responses=RoleSerializer)
    def get(self, request: Request, role_id: str) -> Response:
        return Response(RoleSerializer(get_or_404(roles_queryset(), role_id)).data)

    @extend_schema(
        tags=TAGS,
        summary="Update a custom platform role (step-up)",
        request=RoleUpdateSerializer,
        responses=RoleSerializer,
    )
    def patch(self, request: Request, role_id: str) -> Response:
        role = get_or_404(roles_queryset(), role_id)
        data = RoleUpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        with service_errors():
            services.update_role(
                actor=_actor(request),
                role=role,
                changes=data.validated_data,
                request=request._request,
            )
        return Response(RoleSerializer(get_or_404(roles_queryset(), role_id)).data)

    @extend_schema(
        tags=TAGS, summary="Delete a custom platform role (step-up)", responses={204: None}
    )
    def delete(self, request: Request, role_id: str) -> Response:
        role = get_or_404(roles_queryset(), role_id)
        with service_errors():
            services.delete_role(actor=_actor(request), role=role, request=request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserPlatformRolesView(CsrfProtectedView):
    permission_classes = [
        HasPermission({"GET": "identity.user.view", "POST": "rbac.platform_role.assign"})
    ]

    @extend_schema(
        tags=TAGS, summary="A user's platform roles", responses=AssignmentSerializer(many=True)
    )
    def get(self, request: Request, user_id: str) -> Response:
        user = get_or_404(User.objects.all(), user_id)
        rows = PlatformRoleAssignment.objects.filter(user=user).select_related("role")
        return Response(AssignmentSerializer(rows, many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Grant a platform role (step-up; audited)",
        request=GrantSerializer,
        responses={201: AssignmentSerializer},
    )
    def post(self, request: Request, user_id: str) -> Response:
        user = get_or_404(User.objects.all(), user_id)
        data = GrantSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        role = get_or_404(
            Role.objects.filter(kind=RoleKind.PLATFORM, tenant_id__isnull=True),
            data.validated_data["role"],
        )
        with service_errors():
            assignment = services.grant_platform_role(
                actor=_actor(request),
                user=user,
                role=role,
                reason=data.validated_data["reason"],
                request=request._request,
            )
        return Response(AssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)


class UserPlatformRoleDetailView(CsrfProtectedView):
    permission_classes = [HasPermission({"DELETE": "rbac.platform_role.assign"})]

    @extend_schema(
        tags=TAGS, summary="Revoke a platform role (step-up; audited)", responses={204: None}
    )
    def delete(self, request: Request, user_id: str, assignment_id: str) -> Response:
        user = get_or_404(User.objects.all(), user_id)
        assignment = get_or_404(PlatformRoleAssignment.objects.filter(user=user), assignment_id)
        with service_errors():
            services.revoke_platform_role(
                actor=_actor(request), assignment=assignment, request=request._request
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
