"""Admissions back-office API (Phase 6 M4; ADR-065). Tenant host only, module ``admissions``.

Lists need an institution (or a cycle) and answer 404 outside the caller's institutions;
applicant data needs ``admissions.application.view`` there. Writes go to the services, which
re-check the exact institution scope uncached.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Count
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from apps.admissions import merit, services
from apps.admissions.api import serializers as s
from apps.admissions.models import (
    Application,
    Cycle,
    CycleTarget,
    Inquiry,
    Test,
    TestAssignment,
)
from apps.files.api.serializers import DownloadSerializer
from apps.files.api.serializers import StoredFileSerializer as DocumentSerializer
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
        rows = Cycle.objects.filter(institution=inst).prefetch_related("targets__unit")
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


# --------------------------------------------------------------------------- documents (M5)
class ApplicationDocumentsView(AdmissionsView):
    permission_classes = [HasTenantPermission({"GET": "admissions.application.view"})]

    @extend_schema(
        tags=TAGS, summary="Documents of an application", responses=DocumentSerializer(many=True)
    )
    def get(self, request: Request, application_id: str) -> Response:
        from apps.files.models import StoredFile

        row = _visible(request, Application, application_id, "admissions.application.view")
        files = StoredFile.objects.filter(
            owner_type="admissions.application", owner_id=row.pk
        ).exclude(status=StoredFile.Status.DELETED)
        return Response(DocumentSerializer(files.order_by("created_at"), many=True).data)


class ApplicationDocumentDownloadView(AdmissionsView):
    permission_classes = [HasTenantPermission({"GET": "admissions.application.view"})]

    @extend_schema(
        tags=TAGS,
        summary="A short-lived download link for a document",
        responses=DownloadSerializer,
    )
    def get(self, request: Request, application_id: str, file_id: str) -> Response:
        from apps.files import services as file_services
        from apps.files import storage
        from apps.files.models import StoredFile

        row = _visible(request, Application, application_id, "admissions.application.view")
        document = StoredFile.objects.filter(
            pk=file_id, owner_type="admissions.application", owner_id=row.pk
        ).first() if _is_uuid(file_id) else None  # fmt: skip
        if document is None:
            raise NotFound()
        with service_errors():
            url = file_services.download_url(file=document)
        return Response(
            DownloadSerializer(
                {
                    "url": url,
                    "scan_state": document.scan_state,
                    "expires_in": storage.DOWNLOAD_SECONDS,
                }
            ).data
        )


# --------------------------------------------------------------------------- tests (M6)
class CycleTestsView(AdmissionsView):
    permission_classes = [
        HasTenantPermission({"GET": "admissions.test.manage", "POST": "admissions.test.manage"})
    ]

    @extend_schema(
        tags=TAGS, summary="Admission tests of a cycle", responses=s.TestSerializer(many=True)
    )
    def get(self, request: Request, cycle_id: str) -> Response:
        cycle = _visible(request, Cycle, cycle_id, "admissions.test.manage")
        rows = Test.objects.filter(cycle=cycle).annotate(seated=Count("assignments"))
        return Response(s.TestSerializer(rows.order_by("starts_at"), many=True).data)

    @extend_schema(
        tags=TAGS, summary="Schedule an admission test", request=s.TestCreateSerializer,
        responses={201: s.TestSerializer},
    )  # fmt: skip
    def post(self, request: Request, cycle_id: str) -> Response:
        cycle = _visible(request, Cycle, cycle_id, "admissions.test.manage")
        v = _valid(s.TestCreateSerializer, request.data)
        with service_errors():
            row = merit.create_test(
                actor=_actor(request), cycle=cycle, request=request._request, **v
            )
        row.seated = 0  # type: ignore[attr-defined]
        return Response(s.TestSerializer(row).data, status=status.HTTP_201_CREATED)


class InstitutionTestsView(AdmissionsView):
    """Tests of an institution for those who score them (exam controllers have no cycle view)."""

    permission_classes = [HasTenantPermission({"GET": "admissions.test.score"})]

    @extend_schema(
        tags=TAGS, summary="Admission tests of an institution (newest first)",
        parameters=[INSTITUTION], responses=s.TestSerializer(many=True),
    )  # fmt: skip
    def get(self, request: Request) -> Response:
        with service_errors():
            inst = _institution_param(request, "admissions.test.score")
        rows = Test.objects.filter(institution=inst).annotate(seated=Count("assignments"))
        return Response(s.TestSerializer(rows.order_by("-starts_at")[:200], many=True).data)


class TestAssignmentsView(AdmissionsView):
    permission_classes = [
        HasTenantPermission({"GET": "admissions.test.score", "POST": "admissions.test.manage"})
    ]

    @extend_schema(
        tags=TAGS, summary="Seat list of a test", responses=s.TestSeatSerializer(many=True)
    )
    def get(self, request: Request, test_id: str) -> Response:
        test = _visible(request, Test, test_id, "admissions.test.score")
        rows = TestAssignment.objects.filter(test=test).select_related("application")
        return Response(s.TestSeatSerializer(rows.order_by("seat"), many=True).data)

    @extend_schema(
        tags=TAGS, summary="Seat an application", request=s.TestSeatCreateSerializer,
        responses={201: s.TestSeatSerializer},
    )  # fmt: skip
    def post(self, request: Request, test_id: str) -> Response:
        test = _visible(request, Test, test_id, "admissions.test.manage")
        v = _valid(s.TestSeatCreateSerializer, request.data)
        application = Application.objects.filter(
            pk=v["application"], cycle_id=test.cycle_id
        ).first()
        with service_errors():
            if application is None:
                raise ValidationError({"application": "Choose an application of this cycle."})
            row = merit.assign_test(
                actor=_actor(request), test=test, application=application,
                request=request._request,
            )  # fmt: skip
        return Response(s.TestSeatSerializer(row).data, status=status.HTTP_201_CREATED)


class AssignmentScoreView(AdmissionsView):
    permission_classes = [HasTenantPermission({"PATCH": "admissions.test.score"})]

    @extend_schema(
        tags=TAGS, summary="Enter a score (or an absence)", request=s.ScoreSerializer,
        responses=s.TestSeatSerializer,
    )  # fmt: skip
    def patch(self, request: Request, assignment_id: str) -> Response:
        row = _get(TestAssignment, assignment_id)
        test = _visible(request, Test, row.test_id, "admissions.test.score")
        v = _valid(s.ScoreSerializer, request.data)
        with service_errors():
            row = merit.record_score(
                actor=_actor(request), assignment=row, request=request._request, **v
            )
        assert test  # noqa: S101 - visibility checked above
        return Response(s.TestSeatSerializer(row).data)


class ApplicationEvaluateView(AdmissionsView):
    permission_classes = [HasTenantPermission({"POST": "admissions.application.review"})]

    @extend_schema(
        tags=TAGS, summary="Mark an application evaluated (cycles without tests)", request=None,
        responses=s.ApplicationSerializer,
    )  # fmt: skip
    def post(self, request: Request, application_id: str) -> Response:
        with service_errors():
            row = merit.mark_evaluated(
                actor=_actor(request), application=_get(Application, application_id),
                request=request._request,
            )  # fmt: skip
        return Response(s.ApplicationSerializer(row).data)


# --------------------------------------------------------------------------- merit (M6)
def _merit_payload(target: CycleTarget) -> dict[str, Any]:
    names = dict(Application.objects.filter(target=target).values_list("id", "applicant_name"))
    published = merit.latest(target)
    if published is not None:
        published.ranking = [  # names are not frozen in the list (personal data)
            {**row, "applicant_name": names.get(_uuid(row["application"]), "")}
            for row in published.ranking
        ]
    return {"preview": merit.ranking(target), "published": published}


def _uuid(value: str) -> Any:
    import uuid

    return uuid.UUID(value)


class TargetMeritView(AdmissionsView):
    permission_classes = [HasTenantPermission({"GET": "admissions.application.view"})]

    @extend_schema(
        tags=TAGS, summary="Merit ranking of a target: preview and the latest publication",
        responses=s.MeritSerializer,
    )  # fmt: skip
    def get(self, request: Request, target_id: str) -> Response:
        target = _visible(request, CycleTarget, target_id, "admissions.application.view")
        with service_errors():
            data = _merit_payload(target)
        return Response(s.MeritSerializer(data).data)


class TargetMeritPublishView(AdmissionsView):
    permission_classes = [HasTenantPermission({"POST": "admissions.merit.publish"})]

    @extend_schema(
        tags=TAGS, summary="Publish the merit list (a new frozen version)", request=None,
        responses={201: s.MeritListSerializer},
    )  # fmt: skip
    def post(self, request: Request, target_id: str) -> Response:
        target = _visible(request, CycleTarget, target_id, "admissions.merit.publish")
        with service_errors():
            row = merit.publish(actor=_actor(request), target=target, request=request._request)
        return Response(s.MeritListSerializer(row).data, status=status.HTTP_201_CREATED)


class TargetMeritOffersView(AdmissionsView):
    permission_classes = [HasTenantPermission({"POST": "admissions.application.decide"})]

    @extend_schema(
        tags=TAGS, summary="Offer the free seats down the published merit list", request=None,
        responses=s.ApplicationSerializer(many=True),
    )  # fmt: skip
    def post(self, request: Request, target_id: str) -> Response:
        target = _visible(request, CycleTarget, target_id, "admissions.application.decide")
        with service_errors():
            rows = merit.offer_by_merit(
                actor=_actor(request), target=target, request=request._request
            )
        return Response(s.ApplicationSerializer(rows, many=True).data)


def _is_uuid(value: str) -> bool:
    import uuid

    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True
