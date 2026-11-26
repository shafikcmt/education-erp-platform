"""Staff API (Phase 7 M3; ADR-070, ADR-073). Tenant host only, module ``staff``.

Profiles go through the relationship selectors: staff see profiles in their organisational
scope, and everyone sees their own profile; anything else answers 404. Departments,
designations and advisors are listed per institution the member can see with the right code
(404 otherwise). Writes go to the services, which re-check the exact institution scope uncached.
Custom-field values are masked by their view permission.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from apps.identity.api.utils import get_or_404, service_errors
from apps.identity.models import User
from apps.rbac.engine import ScopeTarget
from apps.staff import selectors, services
from apps.staff.api import serializers as s
from apps.staff.models import Department, Designation, StaffProfile, UnitAdvisor
from apps.tenancy.api.permissions import (
    HasTenantAnyPermission,
    HasTenantPermission,
    visible_institution,
)
from apps.tenancy.api.views_tenant import TenantView

TAGS = ["staff"]
OFFERING_VIEW = "academics.offering.view"


def _actor(request: Request) -> User:
    assert isinstance(request.user, User)  # noqa: S101 - permission classes guarantee it
    return request.user


def _valid(serializer: Any, data: Any, *, partial: bool = False) -> dict[str, Any]:
    form = serializer(data=data, partial=partial)
    form.is_valid(raise_exception=True)
    return dict(form.validated_data)


def _institution(request: Request, codes: tuple[str, ...], institution_id: Any) -> Any:
    """The institution when the member holds one of ``codes`` there (or at one of its
    campuses); 404 otherwise."""
    for code in codes:
        try:
            return visible_institution(_actor(request), code, institution_id)
        except NotFound:
            continue
    raise NotFound()


def _profile(request: Request, profile_id: str) -> StaffProfile:
    row = selectors.visible_profile(_actor(request), profile_id)
    if row is None:
        raise NotFound()
    return row


def _detail(request: Request, profile: StaffProfile) -> dict[str, Any]:
    from apps.customization.fields import visible_values

    actor = _actor(request)
    data = dict(s.StaffProfileSerializer(profile).data)
    data["extra"] = visible_values(
        services.ENTITY,
        profile.extra,
        actor,
        ScopeTarget(profile.tenant_id, profile.institution_id),
    )
    data["advising"] = s.AdvisorSerializer(
        profile.advised_units.select_related("unit", "year", "staff").order_by("-year__start_date"),
        many=True,
    ).data
    mine = selectors.memberships(actor)
    data["relation"] = "self" if profile.membership_id in mine else "staff"
    return data


class StaffBaseView(TenantView):
    module_code = "staff"


# --------------------------------------------------------------------------- profiles
class StaffView(StaffBaseView):
    permission_classes = [HasTenantAnyPermission(selectors.VIEW, selectors.OWN)]

    def get_permissions(self) -> list[Any]:
        if self.request.method == "POST":
            return [HasTenantPermission(services.MANAGE)()]
        return super().get_permissions()

    @extend_schema(
        tags=TAGS,
        summary="Staff profiles I may see (my scope, and my own)",
        parameters=[
            OpenApiParameter("institution", str),
            OpenApiParameter("department", str),
            OpenApiParameter("designation", str),
            OpenApiParameter("status", str),
            OpenApiParameter("q", str, description="Name or number contains"),
        ],
        responses=s.StaffProfileSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        rows = selectors.visible_profiles(_actor(request)).select_related(
            "department", "designation"
        )
        params = request.query_params
        try:
            for field in ("institution", "department", "designation"):
                if value := params.get(field):
                    rows = rows.filter(**{f"{field}_id": value})
            if value := params.get("status"):
                rows = rows.filter(status=value[:16])
            if value := params.get("q"):
                rows = rows.filter(Q(name__icontains=value[:80]) | Q(number__icontains=value[:80]))
            data = s.StaffProfileSerializer(rows.order_by("name", "number")[:500], many=True).data
        except (ValueError, ValidationError):
            raise NotFound() from None
        return Response(data)

    @extend_schema(
        tags=TAGS, summary="Create a staff profile", request=s.StaffCreateSerializer,
        responses={201: s.StaffProfileDetailSerializer},
    )  # fmt: skip
    def post(self, request: Request) -> Response:
        v = _valid(s.StaffCreateSerializer, request.data)
        links = v["links"]
        with service_errors():
            inst = visible_institution(_actor(request), services.MANAGE, v["institution"])
            row = services.create_profile(
                actor=_actor(request), institution=inst, values=v["values"], extra=v["extra"],
                number=v["number"], campus=links.get("campus"),
                department=links.get("department"), designation=links.get("designation"),
                membership=links.get("membership"),
                employment_type=links.get("employment_type", StaffProfile.Employment.PERMANENT),
                request=request._request,
            )  # fmt: skip
        return Response(_detail(request, row), status=status.HTTP_201_CREATED)


class StaffDetailView(StaffBaseView):
    permission_classes = [HasTenantAnyPermission(selectors.VIEW, selectors.OWN)]

    def get_permissions(self) -> list[Any]:
        if self.request.method == "PATCH":
            return [HasTenantPermission(services.MANAGE)()]
        return super().get_permissions()

    @extend_schema(tags=TAGS, summary="A staff profile", responses=s.StaffProfileDetailSerializer)
    def get(self, request: Request, profile_id: str) -> Response:
        return Response(_detail(request, _profile(request, profile_id)))

    @extend_schema(
        tags=TAGS, summary="Change a staff profile", request=s.StaffUpdateSerializer,
        responses=s.StaffProfileDetailSerializer,
    )  # fmt: skip
    def patch(self, request: Request, profile_id: str) -> Response:
        row = _profile(request, profile_id)
        v = _valid(s.StaffUpdateSerializer, request.data)
        with service_errors():
            row = services.update_profile(
                actor=_actor(request), profile=row, values=v.get("values"), extra=v.get("extra"),
                links=v.get("links"), request=request._request,
            )  # fmt: skip
        return Response(_detail(request, row))


# --------------------------------------------------------------------------- structure
STRUCTURE_READ = (selectors.VIEW, services.STRUCTURE)
INSTITUTION = OpenApiParameter("institution", str, required=True)


class DepartmentsView(StaffBaseView):
    permission_classes = [HasTenantAnyPermission(*STRUCTURE_READ)]

    def get_permissions(self) -> list[Any]:
        if self.request.method == "POST":
            return [HasTenantPermission(services.STRUCTURE)()]
        return super().get_permissions()

    @extend_schema(
        tags=TAGS, summary="Departments of an institution", parameters=[INSTITUTION],
        responses=s.DepartmentSerializer(many=True),
    )  # fmt: skip
    def get(self, request: Request) -> Response:
        inst = _institution(request, STRUCTURE_READ, request.query_params.get("institution"))
        rows = Department.objects.filter(institution=inst).order_by("code")
        return Response(s.DepartmentSerializer(rows, many=True).data)

    @extend_schema(
        tags=TAGS, summary="Create a department", request=s.DepartmentCreateSerializer,
        responses={201: s.DepartmentSerializer},
    )  # fmt: skip
    def post(self, request: Request) -> Response:
        v = _valid(s.DepartmentCreateSerializer, request.data)
        inst = visible_institution(_actor(request), services.STRUCTURE, v.pop("institution"))
        with service_errors():
            row = services.create_department(
                actor=_actor(request), institution=inst, request=request._request, **v
            )
        return Response(s.DepartmentSerializer(row).data, status=status.HTTP_201_CREATED)


class DepartmentDetailView(StaffBaseView):
    permission_classes = [HasTenantPermission({"PATCH": services.STRUCTURE})]

    @extend_schema(
        tags=TAGS, summary="Change, move or archive a department",
        request=s.DepartmentUpdateSerializer, responses=s.DepartmentSerializer,
    )  # fmt: skip
    def patch(self, request: Request, department_id: str) -> Response:
        row = get_or_404(Department.objects.all(), department_id)
        visible_institution(_actor(request), services.STRUCTURE, row.institution_id)
        changes = _valid(s.DepartmentUpdateSerializer, request.data)
        with service_errors():
            row = services.update_department(
                actor=_actor(request), department=row, changes=changes, request=request._request
            )
        return Response(s.DepartmentSerializer(row).data)


class DesignationsView(StaffBaseView):
    permission_classes = [HasTenantAnyPermission(*STRUCTURE_READ)]

    def get_permissions(self) -> list[Any]:
        if self.request.method == "POST":
            return [HasTenantPermission(services.STRUCTURE)()]
        return super().get_permissions()

    @extend_schema(
        tags=TAGS, summary="Designations of an institution", parameters=[INSTITUTION],
        responses=s.DesignationSerializer(many=True),
    )  # fmt: skip
    def get(self, request: Request) -> Response:
        inst = _institution(request, STRUCTURE_READ, request.query_params.get("institution"))
        rows = Designation.objects.filter(institution=inst).order_by("code")
        return Response(s.DesignationSerializer(rows, many=True).data)

    @extend_schema(
        tags=TAGS, summary="Create a designation", request=s.DesignationCreateSerializer,
        responses={201: s.DesignationSerializer},
    )  # fmt: skip
    def post(self, request: Request) -> Response:
        v = _valid(s.DesignationCreateSerializer, request.data)
        inst = visible_institution(_actor(request), services.STRUCTURE, v.pop("institution"))
        with service_errors():
            row = services.create_designation(
                actor=_actor(request), institution=inst, request=request._request, **v
            )
        return Response(s.DesignationSerializer(row).data, status=status.HTTP_201_CREATED)


class DesignationDetailView(StaffBaseView):
    permission_classes = [HasTenantPermission({"PATCH": services.STRUCTURE})]

    @extend_schema(
        tags=TAGS, summary="Rename or archive a designation",
        request=s.DesignationUpdateSerializer, responses=s.DesignationSerializer,
    )  # fmt: skip
    def patch(self, request: Request, designation_id: str) -> Response:
        row = get_or_404(Designation.objects.all(), designation_id)
        visible_institution(_actor(request), services.STRUCTURE, row.institution_id)
        changes = _valid(s.DesignationUpdateSerializer, request.data)
        with service_errors():
            row = services.update_designation(
                actor=_actor(request), designation=row, changes=changes, request=request._request
            )
        return Response(s.DesignationSerializer(row).data)


# --------------------------------------------------------------------------- advisors
class AdvisorsView(StaffBaseView):
    permission_classes = [HasTenantPermission({"GET": OFFERING_VIEW, "POST": services.ADVISORS})]

    @extend_schema(
        tags=TAGS, summary="Class teachers (advisors) of an institution",
        parameters=[INSTITUTION, OpenApiParameter("year", str)],
        responses=s.AdvisorSerializer(many=True),
    )  # fmt: skip
    def get(self, request: Request) -> Response:
        inst = _institution(request, (OFFERING_VIEW,), request.query_params.get("institution"))
        rows = UnitAdvisor.objects.filter(institution_id=inst.pk).select_related(
            "unit", "year", "staff"
        )
        try:
            if year := request.query_params.get("year"):
                rows = rows.filter(year_id=uuid.UUID(year))
            data = s.AdvisorSerializer(rows.order_by("unit__code", "-is_primary"), many=True).data
        except (ValueError, ValidationError):
            raise NotFound() from None
        return Response(data)

    @extend_schema(
        tags=TAGS, summary="Make a staff member a class teacher (advisor) of a unit",
        request=s.AdvisorCreateSerializer, responses={201: s.AdvisorSerializer},
    )  # fmt: skip
    def post(self, request: Request) -> Response:
        v = _valid(s.AdvisorCreateSerializer, request.data)
        staff = _profile(request, str(v["staff"]))
        with service_errors():
            row = services.assign_advisor(
                actor=_actor(request), year=v["year"], unit=v["unit"], staff=staff,
                is_primary=v["is_primary"], request=request._request,
            )  # fmt: skip
        return Response(s.AdvisorSerializer(row).data, status=status.HTTP_201_CREATED)


class AdvisorDetailView(StaffBaseView):
    permission_classes = [HasTenantPermission({"DELETE": services.ADVISORS})]

    @extend_schema(tags=TAGS, summary="Remove a class teacher (advisor)", responses={204: None})
    def delete(self, request: Request, advisor_id: str) -> Response:
        row = get_or_404(UnitAdvisor.objects.all(), advisor_id)
        visible_institution(_actor(request), services.ADVISORS, row.institution_id)
        with service_errors():
            services.remove_advisor(actor=_actor(request), advisor=row, request=request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)
