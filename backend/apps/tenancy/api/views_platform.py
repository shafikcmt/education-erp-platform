"""Platform-host tenancy API (Phase 3 M8; plan §12.2, §6.3).

Every view here is platform-host only and declares the catalogue operation of each method in
``platform_operations`` (a CI test checks it against the catalogue). The views only read the
registry (P8) or call the registry services, which run the operation inside
``platform_scope`` with the permission checked again, uncached. No view reads tenant-owned
data: D8 (no cross-tenant lists) and D3 (no tenant audit log on the platform host).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.pagination import StandardCursorPagination
from apps.core.tenancy.platform import platform_scope
from apps.identity.api.utils import CsrfProtectedView, get_or_404, service_errors
from apps.identity.models import User
from apps.rbac.permissions import HasPermission
from apps.tenancy.api import serializers as s
from apps.tenancy.models import Tenant
from apps.tenancy.rules import TenantStatus
from apps.tenancy.selectors.platform import memberships_of, support_sessions_of
from apps.tenancy.services import registry
from apps.tenancy.services import support as support_services

TAGS = ["platform-tenants"]


def _actor(request: Request) -> User:
    assert isinstance(request.user, User)  # noqa: S101 - permission classes guarantee it
    return request.user


def _registry() -> Any:
    return Tenant.objects.exclude(status__in=(TenantStatus.DELETED,))


def sign_in_url(slug: str) -> str | None:
    """The tenant host's sign-in page, or ``None`` while tenant hosts are disabled (D1)."""
    if not settings.TENANT_HOSTS_ENABLED or not settings.TENANT_BASE_DOMAIN:
        return None
    base = urlsplit(settings.FRONTEND_BASE_URL)
    port = f":{base.port}" if base.port else ""
    return f"{base.scheme}://{slug}.{settings.TENANT_BASE_DOMAIN}{port}/"


class RegistryPagination(StandardCursorPagination):
    ordering = ("slug", "id")  # type: ignore[assignment]  # DRF accepts a tuple


class MyMembershipsView(CsrfProtectedView):
    """P2: "My institutions" through F2, own account only."""

    permission_classes = [HasPermission("identity.account.view_own")]
    platform_operations = {"GET": "P2"}

    @extend_schema(
        tags=["me"],
        summary="My organisations (own memberships)",
        responses=s.MembershipSummarySerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        with platform_scope(operation="P2", actor=request.user, reason="own memberships"):
            rows = memberships_of()
        data = [
            {
                "tenant_id": row.tenant_id,
                "slug": row.slug,
                "name": row.name,
                "tenant_status": row.tenant_status,
                "membership_status": row.membership_status,
                "sign_in_url": sign_in_url(row.slug),
            }
            for row in rows
        ]
        return Response(s.MembershipSummarySerializer(data, many=True).data)


class PlatformTenantsView(CsrfProtectedView):
    permission_classes = [
        HasPermission({"GET": "tenancy.tenant.view_any", "POST": "tenancy.tenant.create"})
    ]
    platform_operations = {"GET": "P8", "POST": "P4"}

    @extend_schema(
        tags=TAGS,
        operation_id="platform_tenants_list",
        summary="Tenant registry (registry fields only)",
        parameters=[
            OpenApiParameter("status", OpenApiTypes.STR),
            OpenApiParameter("q", OpenApiTypes.STR, description="Slug or name contains"),
            OpenApiParameter("cursor", OpenApiTypes.STR),
            OpenApiParameter("page_size", OpenApiTypes.INT),
        ],
        responses=s.TenantRegistryPageSerializer,
    )
    def get(self, request: Request) -> Response:
        with platform_scope(
            operation="P8",
            actor=request.user,
            reason="tenant registry",
            permission="tenancy.tenant.view_any",
        ):
            rows = _registry()
            if value := request.query_params.get("status"):
                rows = rows.filter(status=value[:16])
            if value := request.query_params.get("q"):
                term = value.strip()[:64]
                rows = rows.filter(slug__icontains=term) | rows.filter(name__icontains=term)
            paginator = RegistryPagination()
            page = paginator.paginate_queryset(rows, request, view=self)
            data = s.TenantRegistrySerializer(page, many=True).data
        return paginator.get_paginated_response(data)

    @extend_schema(
        tags=TAGS,
        summary="Provision a tenant (first institution, main campus, owner invitation)",
        request=s.ProvisionSerializer,
        responses={201: s.TenantRegistrySerializer},
    )
    def post(self, request: Request) -> Response:
        data = s.ProvisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        first = values.pop("institution")
        with service_errors():
            tenant = registry.provision_tenant(
                actor=_actor(request),
                slug=values["slug"],
                name=values["name"],
                owner_email=values["owner_email"],
                institution=registry.FirstInstitution(**first),
                default_locale=values["default_locale"],
                locales=values.get("locales"),
                timezone_name=values["timezone"],
                currency=values["currency"],
                country=values["country"],
                request=request._request,
            )
        return Response(s.TenantRegistrySerializer(tenant).data, status=status.HTTP_201_CREATED)


class PlatformTenantDetailView(CsrfProtectedView):
    permission_classes = [
        HasPermission({"GET": "tenancy.tenant.view_any", "PATCH": "tenancy.tenant.update_any"})
    ]
    platform_operations = {"GET": "P8", "PATCH": "P5"}

    @extend_schema(tags=TAGS, summary="Tenant registry entry", responses=s.TenantRegistrySerializer)
    def get(self, request: Request, tenant_id: str) -> Response:
        with platform_scope(
            operation="P8",
            actor=request.user,
            reason="tenant registry entry",
            permission="tenancy.tenant.view_any",
        ):
            tenant = get_or_404(_registry(), tenant_id)
        return Response(s.TenantRegistrySerializer(tenant).data)

    @extend_schema(
        tags=TAGS,
        summary="Update registry fields",
        request=s.RegistryUpdateSerializer,
        responses=s.TenantRegistrySerializer,
    )
    def patch(self, request: Request, tenant_id: str) -> Response:
        data = s.RegistryUpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        tenant = get_or_404(_registry(), tenant_id)
        with service_errors():
            tenant = registry.update_registry(
                actor=_actor(request),
                tenant_id=tenant.pk,
                changes=dict(data.validated_data),
                request=request._request,
            )
        return Response(s.TenantRegistrySerializer(tenant).data)


class _StatusChangeView(CsrfProtectedView):
    permission_classes = [HasPermission({"POST": "tenancy.tenant.suspend"})]
    platform_operations = {"POST": "P5"}
    service: Any = None

    def post(self, request: Request, tenant_id: str) -> Response:
        data = s.RegistryReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        tenant = get_or_404(_registry(), tenant_id)
        with service_errors():
            tenant = type(self).service(
                actor=_actor(request),
                tenant_id=tenant.pk,
                reason=data.validated_data["reason"],
                request=request._request,
            )
        return Response(s.TenantRegistrySerializer(tenant).data)


class SuspendTenantView(_StatusChangeView):
    service = staticmethod(registry.suspend_tenant)

    @extend_schema(
        tags=TAGS,
        summary="Suspend a tenant (step-up; revokes support sessions)",
        request=s.RegistryReasonSerializer,
        responses=s.TenantRegistrySerializer,
    )
    def post(self, request: Request, tenant_id: str) -> Response:
        return super().post(request, tenant_id)


class ReactivateTenantView(_StatusChangeView):
    service = staticmethod(registry.reactivate_tenant)

    @extend_schema(
        tags=TAGS,
        summary="Reactivate a suspended tenant (step-up)",
        request=s.RegistryReasonSerializer,
        responses=s.TenantRegistrySerializer,
    )
    def post(self, request: Request, tenant_id: str) -> Response:
        return super().post(request, tenant_id)


class TenantLimitsView(CsrfProtectedView):
    permission_classes = [HasPermission({"PUT": "tenancy.limit.override"})]
    platform_operations = {"PUT": "P5"}

    @extend_schema(
        tags=TAGS,
        summary="Override institution and campus limits (step-up; audited)",
        request=s.LimitsSerializer,
        responses=s.TenantRegistrySerializer,
    )
    def put(self, request: Request, tenant_id: str) -> Response:
        data = s.LimitsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        tenant = get_or_404(_registry(), tenant_id)
        with service_errors():
            tenant = registry.override_limits(
                actor=_actor(request),
                tenant_id=tenant.pk,
                limits=data.limits(),
                reason=data.validated_data["reason"],
                request=request._request,
            )
        return Response(s.TenantRegistrySerializer(tenant).data)


class OwnerInvitationView(CsrfProtectedView):
    permission_classes = [HasPermission({"POST": "tenancy.tenant.create"})]
    platform_operations = {"POST": "P4"}

    @extend_schema(
        tags=TAGS,
        summary="Send or replace the owner invitation",
        request=s.OwnerInvitationSerializer,
        responses={202: None},
    )
    def post(self, request: Request, tenant_id: str) -> Response:
        data = s.OwnerInvitationSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        tenant = get_or_404(_registry(), tenant_id)
        with service_errors():
            registry.resend_owner_invitation(
                actor=_actor(request),
                tenant_id=tenant.pk,
                email=data.validated_data["email"],
                request=request._request,
            )
        return Response(status=status.HTTP_202_ACCEPTED)


class OwnSupportSessionsView(CsrfProtectedView):
    """P6: platform staff request support sessions and list their own (F3)."""

    permission_classes = [HasPermission("tenancy.support_session.request")]
    platform_operations = {"GET": "P6", "POST": "P6"}

    @extend_schema(
        tags=TAGS,
        summary="My support sessions",
        responses=s.OwnSupportSessionSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        with platform_scope(operation="P6", actor=request.user, reason="own support sessions"):
            rows = support_sessions_of()
        return Response(s.OwnSupportSessionSerializer([r.__dict__ for r in rows], many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Request read-only support access to a tenant (step-up)",
        request=s.SupportRequestSerializer,
        responses={201: s.SupportSessionCreatedSerializer},
    )
    def post(self, request: Request) -> Response:
        data = s.SupportRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with service_errors():
            session = support_services.request_session(
                actor=_actor(request),
                tenant_id=data.validated_data["tenant"],
                reason=data.validated_data["reason"],
                ticket_ref=data.validated_data["ticket_ref"],
                minutes=data.validated_data["minutes"],
                request=request._request,
            )
        return Response(
            {"session_id": session.pk, "status": session.status},
            status=status.HTTP_201_CREATED,
        )


class EndOwnSupportSessionView(CsrfProtectedView):
    permission_classes = [HasPermission("tenancy.support_session.request")]
    platform_operations = {"POST": "P6"}

    @extend_schema(
        tags=TAGS,
        summary="End my support session early",
        request=None,
        responses=s.SupportSessionCreatedSerializer,
    )
    def post(self, request: Request, session_id: str) -> Response:
        actor = _actor(request)
        with platform_scope(operation="P6", actor=actor, reason="find own support session"):
            own = {str(r.session_id): r for r in support_sessions_of()}
        found = own.get(session_id)
        if found is None:
            from rest_framework.exceptions import NotFound

            raise NotFound()
        with service_errors():
            session = support_services.end_session(
                actor=actor,
                tenant_id=found.tenant_id,
                session_id=found.session_id,
                request=request._request,
            )
        return Response({"session_id": session.pk, "status": session.status})
