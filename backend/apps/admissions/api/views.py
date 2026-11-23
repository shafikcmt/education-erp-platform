"""Admissions back-office API (Phase 6 M4; ADR-065). Tenant host only, module ``admissions``.

Lists need an institution (or a cycle) and answer 404 outside the caller's institutions;
applicant data needs ``admissions.application.view`` there. Writes go to the services, which
re-check the exact institution scope uncached.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from apps.admissions import services
from apps.admissions.api import serializers as s
from apps.admissions.models import Application, Cycle, Inquiry
from apps.identity.api.utils import service_errors
from apps.identity.models import User
from apps.tenancy.api.permissions import HasTenantPermission, visible_institution
from apps.tenancy.api.views_tenant import TenantView

TAGS = ["admissions"]
INSTITUTION = OpenApiParameter("institution", str, required=True, description="Institution id")


def _actor(request: Request) -> User:
    assert isinstance(request.user, User)  # noqa: S101 - permission classes guarantee it
    return request.user


def _valid(serializer: Any, data: Any, **kwargs: Any) -> dict[str, Any]:
    form = serializer(data=data, **kwargs)
    form.is_valid(raise_exception=True)
    return dict(form.validated_data)


def _get(model: Any, pk: Any) -> Any:
    try:
        row = model.objects.filter(pk=pk).first()
    except (ValueError, ValidationError):
        row = None
    if row is None:
        raise NotFound()
    return row


def _visible(request: Request, model: Any, pk: Any, code: str) -> Any:
    row = _get(model, pk)
    visible_institution(_actor(request), code, row.institution_id)
    return row


def _institution_param(request: Request, code: str) -> Any:
    value = request.query_params.get("institution")
    if not value:
        raise ValidationError({"institution": "Choose an institution."})
    return visible_institution(_actor(request), code, value)


class AdmissionsView(TenantView):
    module_code = "admissions"


# --------------------------------------------------------------------------- inquiries
class InquiriesView(AdmissionsView):
    permission_classes = [
        HasTenantPermission({"GET": "admissions.inquiry.view", "POST": "admissions.inquiry.manage"})
    ]

    @extend_schema(
        tags=TAGS,
        summary="Inquiries of an institution (newest first)",
        parameters=[INSTITUTION, OpenApiParameter("status", str)],
        responses=s.InquirySerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        with service_errors():
            inst = _institution_param(request, "admissions.inquiry.view")
        rows = Inquiry.objects.filter(institution=inst).order_by("-created_at")
        if value := request.query_params.get("status"):
            rows = rows.filter(status=value[:16])
        return Response(s.InquirySerializer(rows[:500], many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Record an inquiry",
        request=s.InquiryCreateSerializer,
        responses={201: s.InquirySerializer},
    )
    def post(self, request: Request) -> Response:
        v = _valid(s.InquiryCreateSerializer, request.data)
        institution = v.pop("institution")
        with service_errors():
            row = services.create_inquiry(
                actor=_actor(request), institution=institution, values=v, request=request._request
            )
        return Response(s.InquirySerializer(row).data, status=status.HTTP_201_CREATED)


class InquiryDetailView(AdmissionsView):
    permission_classes = [HasTenantPermission({"PATCH": "admissions.inquiry.manage"})]

    @extend_schema(
        tags=TAGS,
        summary="Follow up an inquiry",
        request=s.InquiryWriteSerializer,
        responses=s.InquirySerializer,
    )
    def patch(self, request: Request, inquiry_id: str) -> Response:
        v = _valid(s.InquiryWriteSerializer, request.data, partial=True)
        with service_errors():
            row = services.update_inquiry(
                actor=_actor(request),
                inquiry=_get(Inquiry, inquiry_id),
                changes=v,
                request=request._request,
            )
        return Response(s.InquirySerializer(row).data)


# --------------------------------------------------------------------------- cycles
class CyclesView(AdmissionsView):
    permission_classes = [
        HasTenantPermission({"GET": "admissions.cycle.view", "POST": "admissions.cycle.manage"})
    ]

    @extend_schema(
        tags=TAGS,
        summary="Admission cycles of an institution",
        parameters=[INSTITUTION],
        responses=s.CycleSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        with service_errors():
            inst = _institution_param(request, "admissions.cycle.view")
        rows = Cycle.objects.filter(institution=inst).prefetch_related("targets")
        return Response(s.CycleSerializer(rows.order_by("-opens_on"), many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Create an admission cycle",
        request=s.CycleCreateSerializer,
        responses={201: s.CycleSerializer},
    )
    def post(self, request: Request) -> Response:
        v = _valid(s.CycleCreateSerializer, request.data)
        with service_errors():
            cycle = services.create_cycle(actor=_actor(request), request=request._request, **v)
        return Response(s.CycleSerializer(cycle).data, status=status.HTTP_201_CREATED)


class CycleTargetsView(AdmissionsView):
    permission_classes = [HasTenantPermission({"POST": "admissions.cycle.manage"})]

    @extend_schema(
        tags=TAGS,
        summary="Add a target unit with its capacity",
        request=s.TargetCreateSerializer,
        responses={201: s.TargetSerializer},
    )
    def post(self, request: Request, cycle_id: str) -> Response:
        v = _valid(s.TargetCreateSerializer, request.data)
        with service_errors():
            target = services.add_target(
                actor=_actor(request), cycle=_get(Cycle, cycle_id), request=request._request, **v
            )
        return Response(s.TargetSerializer(target).data, status=status.HTTP_201_CREATED)


class CycleStatusView(AdmissionsView):
    permission_classes = [HasTenantPermission({"POST": "admissions.cycle.manage"})]

    @extend_schema(
        tags=TAGS,
        summary="Open, close or archive a cycle",
        request=s.CycleStatusSerializer,
        responses=s.CycleSerializer,
    )
    def post(self, request: Request, cycle_id: str) -> Response:
        v = _valid(s.CycleStatusSerializer, request.data)
        with service_errors():
            cycle = services.set_cycle_status(
                actor=_actor(request),
                cycle=_get(Cycle, cycle_id),
                status=v["status"],
                request=request._request,
            )
        return Response(s.CycleSerializer(cycle).data)


# --------------------------------------------------------------------------- applications
class ApplicationsView(AdmissionsView):
    permission_classes = [
        HasTenantPermission(
            {"GET": "admissions.application.view", "POST": "admissions.application.review"}
        )
    ]

    @extend_schema(
        tags=TAGS,
        summary="Applications of a cycle",
        parameters=[
            OpenApiParameter("cycle", str, required=True, description="Cycle id"),
            OpenApiParameter("status", str),
        ],
        responses=s.ApplicationSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        cycle = _visible(
            request, Cycle, request.query_params.get("cycle") or None, "admissions.application.view"
        )
        rows = Application.objects.filter(cycle=cycle).order_by("submitted_at", "created_at")
        if value := request.query_params.get("status"):
            rows = rows.filter(status=value[:16])
        return Response(s.ApplicationSerializer(rows[:1000], many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Enter an application on an applicant's behalf",
        request=s.ApplicationCreateSerializer,
        responses={201: s.ApplicationSerializer},
    )
    def post(self, request: Request) -> Response:
        v = _valid(s.ApplicationCreateSerializer, request.data)
        with service_errors():
            row = services.create_application(
                actor=_actor(request),
                cycle=_get(Cycle, v["cycle"]),
                target=v["target"],
                values=v["values"],
                request=request._request,
            )
        return Response(s.ApplicationSerializer(row).data, status=status.HTTP_201_CREATED)


class ApplicationDetailView(AdmissionsView):
    permission_classes = [HasTenantPermission({"GET": "admissions.application.view"})]

    @extend_schema(tags=TAGS, summary="An application", responses=s.ApplicationSerializer)
    def get(self, request: Request, application_id: str) -> Response:
        row = _visible(request, Application, application_id, "admissions.application.view")
        return Response(s.ApplicationSerializer(row).data)


class ApplicationReviewView(AdmissionsView):
    permission_classes = [HasTenantPermission({"POST": "admissions.application.review"})]

    @extend_schema(
        tags=TAGS,
        summary="Take a submitted application into review (cycles without a workflow)",
        request=None,
        responses=s.ApplicationSerializer,
    )
    def post(self, request: Request, application_id: str) -> Response:
        with service_errors():
            row = services.start_review(
                actor=_actor(request),
                application=_get(Application, application_id),
                request=request._request,
            )
        return Response(s.ApplicationSerializer(row).data)


class ApplicationDecisionView(AdmissionsView):
    permission_classes = [HasTenantPermission({"POST": "admissions.application.decide"})]

    @extend_schema(
        tags=TAGS,
        summary="Offer a seat or reject",
        request=s.DecisionSerializer,
        responses=s.ApplicationSerializer,
    )
    def post(self, request: Request, application_id: str) -> Response:
        v = _valid(s.DecisionSerializer, request.data)
        with service_errors():
            row = services.decide(
                actor=_actor(request),
                application=_get(Application, application_id),
                request=request._request,
                **v,
            )
        return Response(s.ApplicationSerializer(row).data)


class OfferResponseView(AdmissionsView):
    permission_classes = [HasTenantPermission({"POST": "admissions.application.decide"})]

    @extend_schema(
        tags=TAGS,
        summary="Record the applicant's answer to an offer",
        request=s.OfferResponseSerializer,
        responses=s.ApplicationSerializer,
    )
    def post(self, request: Request, application_id: str) -> Response:
        v = _valid(s.OfferResponseSerializer, request.data)
        with service_errors():
            row = services.record_offer_response(
                actor=_actor(request),
                application=_get(Application, application_id),
                accept=v["accept"],
                request=request._request,
            )
        return Response(s.ApplicationSerializer(row).data)
