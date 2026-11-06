"""Platform user administration (/api/v1/platform/users/...; plan §8).

Every permission here is flagged ``requires_mfa``; deactivate, session revoke and MFA reset are
also ``requires_step_up`` (enforced by ``HasPermission``). Services re-check with
``require_perm`` (defense in depth) and enforce the guard rails.
"""

from django.db.models import Prefetch, QuerySet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.pagination import StandardPageNumberPagination
from apps.identity.api import serializers as s
from apps.identity.api.utils import CsrfProtectedView, get_or_404, service_errors
from apps.identity.models import User
from apps.identity.services import accounts, mfa, sessions
from apps.rbac.engine import has_perm
from apps.rbac.models import PlatformRoleAssignment
from apps.rbac.permissions import HasPermission

TAGS = ["platform-users"]


def _actor(request: Request) -> User:
    assert isinstance(request.user, User)  # noqa: S101 - permission classes guarantee it
    return request.user


def users_queryset() -> QuerySet[User]:
    return User.objects.prefetch_related(
        Prefetch("platform_roles", queryset=PlatformRoleAssignment.objects.select_related("role"))
    ).order_by("email")


def _detail(request: Request, user: User) -> dict[str, object]:
    sensitive = has_perm(request.user, "identity.user.view_sensitive", target=request.scope_target)  # type: ignore[attr-defined]
    serializer = s.PlatformUserSensitiveSerializer if sensitive else s.PlatformUserSerializer
    return dict(serializer(user).data)


class PlatformUsersView(CsrfProtectedView):
    permission_classes = [
        HasPermission({"GET": "identity.user.view", "POST": "identity.user.create"})
    ]

    @extend_schema(
        tags=TAGS,
        summary="List platform users",
        parameters=[OpenApiParameter("search", OpenApiTypes.STR, description="Email contains")],
        responses=s.PlatformUserSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        users = users_queryset()
        if search := request.query_params.get("search", "").strip():
            users = users.filter(email__icontains=search[:100])
        paginator = StandardPageNumberPagination()
        page = paginator.paginate_queryset(users, request, view=self)
        return paginator.get_paginated_response(s.PlatformUserSerializer(page, many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Create a user and send the activation email",
        request=s.PlatformUserCreateSerializer,
        responses={201: s.PlatformUserSerializer},
    )
    def post(self, request: Request) -> Response:
        data = s.PlatformUserCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with service_errors():
            user = accounts.create_user(
                actor=_actor(request), request=request._request, **data.validated_data
            )
        return Response(s.PlatformUserSerializer(user).data, status=status.HTTP_201_CREATED)


class PlatformUserDetailView(CsrfProtectedView):
    permission_classes = [
        HasPermission({"GET": "identity.user.view", "PATCH": "identity.user.update"})
    ]

    @extend_schema(tags=TAGS, summary="User detail", responses=s.PlatformUserSensitiveSerializer)
    def get(self, request: Request, user_id: str) -> Response:
        return Response(_detail(request, get_or_404(users_queryset(), user_id)))

    @extend_schema(
        tags=TAGS,
        summary="Update a user's profile",
        request=s.PlatformUserUpdateSerializer,
        responses=s.PlatformUserSensitiveSerializer,
    )
    def patch(self, request: Request, user_id: str) -> Response:
        user = get_or_404(users_queryset(), user_id)
        data = s.PlatformUserUpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        accounts.admin_update_user(
            actor=_actor(request), user=user, changes=data.validated_data, request=request._request
        )
        return Response(_detail(request, get_or_404(users_queryset(), user_id)))


class _UserAction(CsrfProtectedView):
    def target(self, user_id: str) -> User:
        return get_or_404(users_queryset(), user_id)


class DeactivateUserView(_UserAction):
    permission_classes = [HasPermission("identity.user.deactivate")]

    @extend_schema(
        tags=TAGS,
        summary="Deactivate a user (step-up; signs them out)",
        request=None,
        responses=s.PlatformUserSerializer,
    )
    def post(self, request: Request, user_id: str) -> Response:
        with service_errors():
            user = accounts.deactivate(
                actor=_actor(request), user=self.target(user_id), request=request._request
            )
        return Response(s.PlatformUserSerializer(self.target(str(user.pk))).data)


class ReactivateUserView(_UserAction):
    permission_classes = [HasPermission("identity.user.deactivate")]

    @extend_schema(
        tags=TAGS,
        summary="Reactivate a user (step-up)",
        request=None,
        responses=s.PlatformUserSerializer,
    )
    def post(self, request: Request, user_id: str) -> Response:
        user = accounts.reactivate(
            actor=_actor(request), user=self.target(user_id), request=request._request
        )
        return Response(s.PlatformUserSerializer(self.target(str(user.pk))).data)


class RevokeUserSessionsView(_UserAction):
    permission_classes = [HasPermission("identity.session.revoke_any")]

    @extend_schema(
        tags=TAGS,
        summary="Sign a user out everywhere (step-up)",
        request=None,
        responses=s.RevokedCountSerializer,
    )
    def post(self, request: Request, user_id: str) -> Response:
        count = sessions.revoke_user_sessions(
            self.target(user_id),
            reason="revoked_by_admin",
            actor=_actor(request),
            request=request._request,
        )
        return Response({"revoked": count})


class ResetUserMfaView(_UserAction):
    permission_classes = [HasPermission("identity.mfa.reset")]

    @extend_schema(
        tags=TAGS,
        summary="Reset a user's MFA (step-up + reason)",
        request=s.ReasonSerializer,
        responses={204: None},
    )
    def post(self, request: Request, user_id: str) -> Response:
        data = s.ReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        mfa.admin_reset_mfa(
            _actor(request),
            self.target(user_id),
            reason=data.validated_data["reason"],
            request=request._request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ResendActivationView(_UserAction):
    permission_classes = [HasPermission("identity.user.create")]

    @extend_schema(
        tags=TAGS,
        summary="Resend the activation email",
        request=None,
        responses={202: s.AcceptedSerializer},
    )
    def post(self, request: Request, user_id: str) -> Response:
        accounts.resend_activation(
            actor=_actor(request), user=self.target(user_id), request=request._request
        )
        return Response({"detail": "Activation email sent."}, status=status.HTTP_202_ACCEPTED)
