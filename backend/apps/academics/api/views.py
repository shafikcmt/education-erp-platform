"""Academics API (Phase 6 M2; ADR-063). Tenant host only, module ``academics``.

The permission classes are the first gate (the code held in some scope of this tenant). Lists
need an institution (or year) and answer 404 unless the caller holds the view code at that
institution or one of its campuses; writes go to the services, which re-check the exact
institution scope uncached, validate against the configuration and audit.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from apps.academics import capabilities as caps
from apps.academics import services
from apps.academics.api import serializers as s
from apps.academics.models import AcademicYear, Offering, OfferingTeacher, Subject, Term, Unit
from apps.identity.api.utils import service_errors
from apps.identity.models import User
from apps.tenancy.api.permissions import HasTenantPermission, visible_institution
from apps.tenancy.api.views_tenant import TenantView

TAGS = ["academics"]
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


def _institution_param(request: Request, code: str) -> Any:
    value = request.query_params.get("institution")
    if not value:
        raise ValidationError({"institution": "Choose an institution."})
    return visible_institution(_actor(request), code, value)


class AcademicsView(TenantView):
    module_code = "academics"


# --------------------------------------------------------------------------- setup
class SetupView(AcademicsView):
    permission_classes = [HasTenantPermission({"GET": "academics.structure.view"})]

    @extend_schema(
        tags=TAGS,
        summary="Structure levels and capability flags of an institution",
        parameters=[INSTITUTION],
        responses=s.SetupSerializer,
    )
    def get(self, request: Request) -> Response:
        with service_errors():
            inst = _institution_param(request, "academics.structure.view")
        data = {
            "levels": caps.unit_levels(inst.pk),
            "credit_based": caps.capability(inst.pk, caps.CREDIT_BASED),
            "semester_based": caps.capability(inst.pk, caps.SEMESTER_BASED),
            "section_enabled": caps.capability(inst.pk, caps.SECTION_ENABLED),
        }
        return Response(s.SetupSerializer(data).data)


# --------------------------------------------------------------------------- years and terms
class YearsView(AcademicsView):
    permission_classes = [
        HasTenantPermission({"GET": "academics.year.view", "POST": "academics.year.manage"})
    ]

    @extend_schema(
        tags=TAGS,
        summary="Academic years of an institution",
        parameters=[INSTITUTION],
        responses=s.YearSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        with service_errors():
            inst = _institution_param(request, "academics.year.view")
        rows = AcademicYear.objects.filter(institution=inst).order_by("-start_date")
        return Response(s.YearSerializer(rows, many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Create an academic year",
        request=s.YearCreateSerializer,
        responses={201: s.YearSerializer},
    )
    def post(self, request: Request) -> Response:
        v = _valid(s.YearCreateSerializer, request.data)
        with service_errors():
            year = services.create_year(actor=_actor(request), request=request._request, **v)
        return Response(s.YearSerializer(year).data, status=status.HTTP_201_CREATED)


class YearStatusView(AcademicsView):
    permission_classes = [HasTenantPermission({"POST": "academics.year.manage"})]

    @extend_schema(
        tags=TAGS,
        summary="Activate or close an academic year",
        request=s.YearStatusSerializer,
        responses=s.YearSerializer,
    )
    def post(self, request: Request, year_id: str) -> Response:
        v = _valid(s.YearStatusSerializer, request.data)
        with service_errors():
            year = services.set_year_status(
                actor=_actor(request),
                year=_get(AcademicYear, year_id),
                status=v["status"],
                request=request._request,
            )
        return Response(s.YearSerializer(year).data)


class TermsView(AcademicsView):
    permission_classes = [
        HasTenantPermission({"GET": "academics.year.view", "POST": "academics.year.manage"})
    ]

    @extend_schema(tags=TAGS, summary="Terms of a year", responses=s.TermSerializer(many=True))
    def get(self, request: Request, year_id: str) -> Response:
        year = _get(AcademicYear, year_id)
        visible_institution(_actor(request), "academics.year.view", year.institution_id)
        rows = Term.objects.filter(year=year).order_by("order", "start_date")
        return Response(s.TermSerializer(rows, many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Add a term to a year",
        request=s.TermCreateSerializer,
        responses={201: s.TermSerializer},
    )
    def post(self, request: Request, year_id: str) -> Response:
        v = _valid(s.TermCreateSerializer, request.data)
        with service_errors():
            term = services.create_term(
                actor=_actor(request),
                year=_get(AcademicYear, year_id),
                request=request._request,
                **v,
            )
        return Response(s.TermSerializer(term).data, status=status.HTTP_201_CREATED)


# --------------------------------------------------------------------------- units
class UnitsView(AcademicsView):
    permission_classes = [
        HasTenantPermission(
            {"GET": "academics.structure.view", "POST": "academics.structure.manage"}
        )
    ]

    @extend_schema(
        tags=TAGS,
        summary="Academic units of an institution (flat list with parents)",
        parameters=[
            INSTITUTION,
            OpenApiParameter("archived", bool, description="Include archived units"),
        ],
        responses=s.UnitSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        with service_errors():
            inst = _institution_param(request, "academics.structure.view")
        rows = Unit.objects.filter(institution=inst)
        if request.query_params.get("archived") not in ("true", "1"):
            rows = rows.filter(archived_at__isnull=True)
        return Response(s.UnitSerializer(rows.order_by("order", "code"), many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Create an academic unit",
        request=s.UnitCreateSerializer,
        responses={201: s.UnitSerializer},
    )
    def post(self, request: Request) -> Response:
        v = _valid(s.UnitCreateSerializer, request.data)
        parent = _get(Unit, v.pop("parent")) if v.get("parent") else None
        v.pop("parent", None)
        with service_errors():
            unit = services.create_unit(
                actor=_actor(request), parent=parent, request=request._request, **v
            )
        return Response(s.UnitSerializer(unit).data, status=status.HTTP_201_CREATED)


class UnitDetailView(AcademicsView):
    permission_classes = [HasTenantPermission({"PATCH": "academics.structure.manage"})]

    @extend_schema(
        tags=TAGS,
        summary="Rename or change a unit",
        request=s.UnitUpdateSerializer,
        responses=s.UnitSerializer,
    )
    def patch(self, request: Request, unit_id: str) -> Response:
        v = _valid(s.UnitUpdateSerializer, request.data, partial=True)
        with service_errors():
            unit = services.update_unit(
                actor=_actor(request),
                unit=_get(Unit, unit_id),
                changes=v,
                request=request._request,
            )
        return Response(s.UnitSerializer(unit).data)


class UnitArchiveView(AcademicsView):
    permission_classes = [HasTenantPermission({"POST": "academics.structure.manage"})]

    @extend_schema(tags=TAGS, summary="Archive a unit", request=None, responses=s.UnitSerializer)
    def post(self, request: Request, unit_id: str) -> Response:
        with service_errors():
            unit = services.archive_unit(
                actor=_actor(request), unit=_get(Unit, unit_id), request=request._request
            )
        return Response(s.UnitSerializer(unit).data)


# --------------------------------------------------------------------------- subjects
class SubjectsView(AcademicsView):
    permission_classes = [
        HasTenantPermission({"GET": "academics.subject.view", "POST": "academics.subject.manage"})
    ]

    @extend_schema(
        tags=TAGS,
        summary="Subjects and courses of an institution",
        parameters=[INSTITUTION],
        responses=s.SubjectSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        with service_errors():
            inst = _institution_param(request, "academics.subject.view")
        rows = Subject.objects.filter(institution=inst, archived_at__isnull=True).order_by("code")
        return Response(s.SubjectSerializer(rows, many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Create a subject or course",
        request=s.SubjectCreateSerializer,
        responses={201: s.SubjectSerializer},
    )
    def post(self, request: Request) -> Response:
        v = _valid(s.SubjectCreateSerializer, request.data)
        with service_errors():
            subject = services.create_subject(actor=_actor(request), request=request._request, **v)
        return Response(s.SubjectSerializer(subject).data, status=status.HTTP_201_CREATED)


class SubjectArchiveView(AcademicsView):
    permission_classes = [HasTenantPermission({"POST": "academics.subject.manage"})]

    @extend_schema(
        tags=TAGS, summary="Archive a subject", request=None, responses=s.SubjectSerializer
    )
    def post(self, request: Request, subject_id: str) -> Response:
        with service_errors():
            subject = services.archive_subject(
                actor=_actor(request), subject=_get(Subject, subject_id), request=request._request
            )
        return Response(s.SubjectSerializer(subject).data)


# --------------------------------------------------------------------------- offerings
class OfferingsView(AcademicsView):
    permission_classes = [
        HasTenantPermission({"GET": "academics.offering.view", "POST": "academics.offering.manage"})
    ]

    @extend_schema(
        tags=TAGS,
        summary="Offerings of an academic year",
        parameters=[OpenApiParameter("year", str, required=True, description="Academic year id")],
        responses=s.OfferingSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        year = _get(AcademicYear, request.query_params.get("year") or None)
        visible_institution(_actor(request), "academics.offering.view", year.institution_id)
        rows = Offering.objects.filter(year=year).prefetch_related("teachers")
        return Response(s.OfferingSerializer(rows, many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Offer a subject in a unit for a year (and term)",
        request=s.OfferingCreateSerializer,
        responses={201: s.OfferingSerializer},
    )
    def post(self, request: Request) -> Response:
        v = _valid(s.OfferingCreateSerializer, request.data)
        with service_errors():
            offering = services.create_offering(
                actor=_actor(request),
                year=_get(AcademicYear, v["year"]),
                unit=_get(Unit, v["unit"]),
                subject=_get(Subject, v["subject"]),
                term=_get(Term, v["term"]) if v.get("term") else None,
                credits=v.get("credits"),
                request=request._request,
            )
        return Response(s.OfferingSerializer(offering).data, status=status.HTTP_201_CREATED)


class OfferingTeachersView(AcademicsView):
    permission_classes = [HasTenantPermission({"POST": "academics.offering.manage"})]

    @extend_schema(
        tags=TAGS,
        summary="Assign a teacher (a member) to an offering",
        request=s.TeacherAssignSerializer,
        responses={201: s.TeacherSerializer},
    )
    def post(self, request: Request, offering_id: str) -> Response:
        v = _valid(s.TeacherAssignSerializer, request.data)
        with service_errors():
            row = services.assign_teacher(
                actor=_actor(request),
                offering=_get(Offering, offering_id),
                membership=v["membership"],
                role=v["role"],
                request=request._request,
            )
        return Response(s.TeacherSerializer(row).data, status=status.HTTP_201_CREATED)


class OfferingTeacherDetailView(AcademicsView):
    permission_classes = [HasTenantPermission({"DELETE": "academics.offering.manage"})]

    @extend_schema(tags=TAGS, summary="Remove a teacher from an offering", responses={204: None})
    def delete(self, request: Request, offering_id: str, teacher_id: str) -> Response:
        row = _get(OfferingTeacher, teacher_id)
        if str(row.offering_id) != offering_id:
            raise NotFound()
        with service_errors():
            services.remove_teacher(actor=_actor(request), assignment=row, request=request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)
