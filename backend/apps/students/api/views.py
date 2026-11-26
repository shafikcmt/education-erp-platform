"""Students API (Phase 7 M2; ADR-068, ADR-073). Tenant host only, module ``students``.

Lists and details go through the relationship selectors: staff see students in their
organisational scope, teachers the students they teach, guardians their own children, students
themselves; anything else answers 404. Writes go to the services, which re-check the exact
institution scope uncached. Custom-field values are masked by their view permission.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.identity.api.utils import service_errors
from apps.identity.models import User
from apps.rbac.engine import ScopeTarget
from apps.students import imports, lifecycle, selectors, services
from apps.students.api import serializers as s
from apps.students.models import (
    Guardian,
    ImportJob,
    Student,
    StudentGuardian,
    TransferCertificate,
)
from apps.tenancy.api.permissions import (
    HasTenantAnyPermission,
    HasTenantPermission,
    visible_institution,
)
from apps.tenancy.api.views_tenant import TenantView

TAGS = ["students"]
VIEW_ANY = HasTenantAnyPermission(*selectors.ALL_VIEW_CODES)


def _actor(request: Request) -> User:
    assert isinstance(request.user, User)  # noqa: S101 - permission classes guarantee it
    return request.user


def _valid(serializer: Any, data: Any) -> dict[str, Any]:
    form = serializer(data=data)
    form.is_valid(raise_exception=True)
    return dict(form.validated_data)


def _student(request: Request, student_id: str) -> Student:
    row = selectors.visible_student(_actor(request), student_id)
    if row is None:
        raise NotFound()
    return row


def _relation(actor: User, student: Student) -> str:
    """Why the member sees this student (the UI adapts; the server already decided)."""
    if selectors.holds_in_institution(actor, selectors.VIEW, student.institution_id):
        return "staff"
    mine = selectors.memberships(actor)
    if student.membership_id in mine:
        return "self"
    if student.guardian_links.filter(guardian__membership_id__in=mine).exists():
        return "guardian"
    return "teacher"


def _detail(request: Request, student: Student) -> dict[str, Any]:
    from apps.customization.fields import visible_values

    actor = _actor(request)
    target = ScopeTarget(student.tenant_id, student.institution_id)
    data = dict(s.StudentSerializer(student).data)
    data["extra"] = visible_values(services.STUDENT_ENTITY, student.extra, actor, target)
    data["enrollments"] = s.EnrollmentSerializer(
        student.enrollments.select_related("unit", "year").order_by("-start_date"), many=True
    ).data
    data["guardians"] = s.GuardianLinkSerializer(
        selectors.guardians_shown(actor, student), many=True
    ).data
    data["relation"] = _relation(actor, student)
    return data


class StudentsBaseView(TenantView):
    module_code = "students"


class StudentsView(StudentsBaseView):
    permission_classes = [VIEW_ANY]

    def get_permissions(self) -> list[Any]:
        if self.request.method == "POST":
            return [HasTenantPermission("students.student.manage")()]
        return super().get_permissions()

    @extend_schema(
        tags=TAGS,
        summary="Students I may see (scope, taught, children, myself)",
        parameters=[
            OpenApiParameter("institution", str),
            OpenApiParameter("unit", str, description="Active enrollment in this unit"),
            OpenApiParameter("status", str),
            OpenApiParameter("q", str, description="Name or number contains"),
        ],
        responses=s.StudentSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        rows = selectors.visible_students(_actor(request))
        params = request.query_params
        try:
            if value := params.get("institution"):
                rows = rows.filter(institution_id=value)
            if value := params.get("unit"):
                rows = rows.filter(enrollments__unit_id=value, enrollments__status="active")
            if value := params.get("status"):
                rows = rows.filter(status=value[:16])
            if value := params.get("q"):
                rows = rows.filter(Q(name__icontains=value[:80]) | Q(number__icontains=value[:80]))
            data = s.StudentSerializer(rows.order_by("name", "number")[:500], many=True).data
        except (ValueError, ValidationError):
            raise NotFound() from None
        return Response(data)

    @extend_schema(
        tags=TAGS, summary="Create a student", request=s.StudentCreateSerializer,
        responses={201: s.StudentDetailSerializer},
    )  # fmt: skip
    def post(self, request: Request) -> Response:
        v = _valid(s.StudentCreateSerializer, request.data)
        with service_errors():
            inst = visible_institution(_actor(request), "students.student.manage", v["institution"])
            row = services.create_student(
                actor=_actor(request), institution=inst, values=v["values"], extra=v["extra"],
                number=v["number"], request=request._request,
            )  # fmt: skip
        return Response(_detail(request, row), status=status.HTTP_201_CREATED)


class StudentDetailView(StudentsBaseView):
    permission_classes = [VIEW_ANY]

    def get_permissions(self) -> list[Any]:
        if self.request.method == "PATCH":
            return [HasTenantPermission("students.student.manage")()]
        return super().get_permissions()

    @extend_schema(tags=TAGS, summary="A student", responses=s.StudentDetailSerializer)
    def get(self, request: Request, student_id: str) -> Response:
        return Response(_detail(request, _student(request, student_id)))

    @extend_schema(
        tags=TAGS, summary="Change a student", request=s.StudentUpdateSerializer,
        responses=s.StudentDetailSerializer,
    )  # fmt: skip
    def patch(self, request: Request, student_id: str) -> Response:
        row = _student(request, student_id)
        v = _valid(s.StudentUpdateSerializer, request.data)
        with service_errors():
            row = services.update_student(
                actor=_actor(request), student=row, values=v.get("values"), extra=v.get("extra"),
                request=request._request,
            )  # fmt: skip
        return Response(_detail(request, row))


class StudentGuardiansView(StudentsBaseView):
    permission_classes = [HasTenantPermission({"POST": "students.guardian.manage"})]

    @extend_schema(
        tags=TAGS, summary="Link a guardian (an existing one, or matched/created from values)",
        request=s.GuardianLinkCreateSerializer, responses={201: s.GuardianLinkSerializer},
    )  # fmt: skip
    def post(self, request: Request, student_id: str) -> Response:
        student = _student(request, student_id)
        v = _valid(s.GuardianLinkCreateSerializer, request.data)
        guardian = None
        if v.get("guardian"):
            guardian = Guardian.objects.filter(pk=v["guardian"]).first()
            if guardian is None:
                raise NotFound()
        with service_errors():
            link = services.link_guardian(
                actor=_actor(request), student=student, guardian=guardian,
                values=v.get("values"), extra=v["extra"], relation=v["relation"],
                is_primary=v["is_primary"], can_pickup=v["can_pickup"],
                receives_notices=v["receives_notices"], request=request._request,
            )  # fmt: skip
        return Response(s.GuardianLinkSerializer(link).data, status=status.HTTP_201_CREATED)


class StudentGuardianLinkView(StudentsBaseView):
    permission_classes = [HasTenantPermission({"DELETE": "students.guardian.manage"})]

    @extend_schema(tags=TAGS, summary="Unlink a guardian", responses={204: None})
    def delete(self, request: Request, student_id: str, link_id: str) -> Response:
        student = _student(request, student_id)
        try:
            link = StudentGuardian.objects.filter(pk=link_id, student=student).first()
        except (ValueError, ValidationError):
            link = None
        if link is None:
            raise NotFound()
        with service_errors():
            services.unlink_guardian(actor=_actor(request), link=link, request=request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class StudentEnrollmentsView(StudentsBaseView):
    permission_classes = [HasTenantPermission({"POST": "students.student.manage"})]

    @extend_schema(
        tags=TAGS, summary="Enroll a student in a unit for a year",
        request=s.EnrollmentCreateSerializer, responses={201: s.EnrollmentSerializer},
    )  # fmt: skip
    def post(self, request: Request, student_id: str) -> Response:
        student = _student(request, student_id)
        v = _valid(s.EnrollmentCreateSerializer, request.data)
        with service_errors():
            row = services.enroll(
                actor=_actor(request), student=student, year=v["year"], unit=v["unit"],
                roll_number=v["roll_number"], start_date=v["start_date"],
                request=request._request,
            )  # fmt: skip
        return Response(s.EnrollmentSerializer(row).data, status=status.HTTP_201_CREATED)


class GuardiansView(StudentsBaseView):
    permission_classes = [HasTenantPermission({"GET": "students.guardian.view"})]

    @extend_schema(
        tags=TAGS, summary="Find guardians by phone, email or name (to link or merge)",
        parameters=[OpenApiParameter("q", str, required=True)],
        responses=s.GuardianSerializer(many=True),
    )  # fmt: skip
    def get(self, request: Request) -> Response:
        """Guardians linked to students the member may see, or matching the exact phone/email
        typed (so staff can find an existing guardian before creating a duplicate)."""
        query = (request.query_params.get("q") or "").strip()[:80]
        if len(query) < 3:
            raise DRFValidationError({"q": "Type at least three characters."})
        visible = selectors.visible_students(_actor(request))
        rows = Guardian.objects.filter(student_links__student__in=visible).filter(
            Q(name__icontains=query) | Q(phone__contains=query) | Q(email__icontains=query)
        )
        found = {g.pk: g for g in rows.distinct()[:50]}
        exact = _exact_match(query)
        if exact is not None:
            found[exact.pk] = exact
        return Response(s.GuardianSerializer(list(found.values()), many=True).data)


def _exact_match(query: str) -> Guardian | None:
    """The tenant's guardian with exactly this email or phone, if the query is one."""
    if "@" in query:
        return services.match_guardian(email=query)
    try:
        return services.match_guardian(phone=query)
    except ValidationError:
        return None  # not a phone number either


class GuardianMergeView(StudentsBaseView):
    permission_classes = [HasTenantPermission({"POST": "students.guardian.manage"})]

    @extend_schema(
        tags=TAGS, summary="Merge a duplicate guardian into another",
        request=s.GuardianMergeSerializer, responses=s.GuardianSerializer,
    )  # fmt: skip
    def post(self, request: Request) -> Response:
        v = _valid(s.GuardianMergeSerializer, request.data)
        keep = Guardian.objects.filter(pk=v["keep"]).first()
        duplicate = Guardian.objects.filter(pk=v["duplicate"]).first()
        if keep is None or duplicate is None:
            raise NotFound()
        with service_errors():
            row = services.merge_guardians(
                actor=_actor(request), keep=keep, duplicate=duplicate, request=request._request
            )
        return Response(s.GuardianSerializer(row).data)


class StudentFromApplicationView(StudentsBaseView):
    permission_classes = [HasTenantPermission({"POST": "students.student.manage"})]

    @extend_schema(
        tags=TAGS,
        summary="The student of an accepted application (created and enrolled if needed)",
        request=s.FromApplicationSerializer,
        responses={200: s.StudentDetailSerializer, 201: s.StudentDetailSerializer},
    )
    def post(self, request: Request) -> Response:
        """Runs the conversion that acceptance queues (idempotent): for example after the
        plan's student limit was raised. 404 unless the application is accepted and in an
        institution where the member manages students."""
        from apps.admissions.selectors import accepted_application
        from apps.students.conversion import convert

        v = _valid(s.FromApplicationSerializer, request.data)
        data = accepted_application(v["application"])
        if data is None:
            raise NotFound()
        visible_institution(_actor(request), "students.student.manage", data["institution_id"])
        existed = Student.objects.filter(source_application_id=data["id"]).exists()
        with service_errors():
            row = convert(data["id"], actor=_actor(request), request=request._request,
                          raise_errors=True)  # fmt: skip
        if row is None:
            raise NotFound()
        code = status.HTTP_200_OK if existed else status.HTTP_201_CREATED
        return Response(_detail(request, row), status=code)


# --------------------------------------------------------------------------- lifecycle (M5)
DOCUMENT_PARAMS = [
    OpenApiParameter("template", str, required=True, description="Published template key"),
    OpenApiParameter("locale", str),
]


def _document_args(request: Request) -> tuple[str, str]:
    template = (request.query_params.get("template") or "").strip()[:64]
    if not template:
        raise DRFValidationError({"template": "Choose a template."})
    return template, (request.query_params.get("locale") or "en")[:16]


class StudentMoveView(StudentsBaseView):
    permission_classes = [HasTenantPermission({"POST": "students.student.manage"})]

    @extend_schema(
        tags=TAGS, summary="Move a student to another unit within the year",
        request=s.MoveSerializer, responses={201: s.EnrollmentSerializer},
    )  # fmt: skip
    def post(self, request: Request, student_id: str) -> Response:
        student = _student(request, student_id)
        v = _valid(s.MoveSerializer, request.data)
        with service_errors():
            row = lifecycle.move(
                actor=_actor(request), student=student, unit=v["unit"],
                roll_number=v["roll_number"], request=request._request,
            )  # fmt: skip
        return Response(s.EnrollmentSerializer(row).data, status=status.HTTP_201_CREATED)


class StudentWithdrawView(StudentsBaseView):
    permission_classes = [HasTenantPermission({"POST": "students.student.transfer"})]

    @extend_schema(
        tags=TAGS, summary="Withdraw a student", request=s.WithdrawSerializer,
        responses=s.StudentDetailSerializer,
    )  # fmt: skip
    def post(self, request: Request, student_id: str) -> Response:
        student = _student(request, student_id)
        v = _valid(s.WithdrawSerializer, request.data)
        with service_errors():
            row = lifecycle.withdraw(
                actor=_actor(request), student=student, reason=v["reason"], on=v["on"],
                request=request._request,
            )  # fmt: skip
        return Response(_detail(request, row))


class StudentTransferCertificatesView(StudentsBaseView):
    permission_classes = [
        HasTenantPermission({"GET": "students.student.view", "POST": "students.student.transfer"})
    ]

    @extend_schema(
        tags=TAGS, summary="Transfer certificates of a student",
        responses=s.TransferCertificateSerializer(many=True),
    )  # fmt: skip
    def get(self, request: Request, student_id: str) -> Response:
        student = _student(request, student_id)
        rows = TransferCertificate.objects.filter(student=student).order_by("-issued_on")
        return Response(s.TransferCertificateSerializer(rows, many=True).data)

    @extend_schema(
        tags=TAGS, summary="Issue a transfer certificate (the student leaves)",
        request=s.TransferCertificateCreateSerializer,
        responses={201: s.TransferCertificateSerializer},
    )  # fmt: skip
    def post(self, request: Request, student_id: str) -> Response:
        student = _student(request, student_id)
        v = _valid(s.TransferCertificateCreateSerializer, request.data)
        with service_errors():
            row = lifecycle.issue_transfer_certificate(
                actor=_actor(request), student=student, reason=v["reason"],
                destination=v["destination"], number=v["number"], on=v["on"],
                request=request._request,
            )  # fmt: skip
        return Response(s.TransferCertificateSerializer(row).data, status=status.HTTP_201_CREATED)


class TransferCertificateDocumentView(StudentsBaseView):
    permission_classes = [HasTenantPermission({"GET": "students.student.view"})]

    @extend_schema(
        tags=TAGS, summary="Printable transfer certificate (HTML from a Studio template)",
        parameters=DOCUMENT_PARAMS, responses=s.DocumentSerializer,
    )  # fmt: skip
    def get(self, request: Request, student_id: str, certificate_id: str) -> Response:
        student = _student(request, student_id)
        template, locale = _document_args(request)
        try:
            row = TransferCertificate.objects.filter(pk=certificate_id, student=student).first()
        except (ValueError, ValidationError):
            row = None
        if row is None:
            raise NotFound()
        with service_errors():
            html = lifecycle.transfer_certificate_document(
                actor=_actor(request), certificate=row, template_key=template, locale=locale
            )
        return Response({"html": html})


class StudentIdCardView(StudentsBaseView):
    permission_classes = [HasTenantPermission({"GET": "students.student.view"})]

    @extend_schema(
        tags=TAGS, summary="Printable ID card (HTML from a Studio template)",
        parameters=DOCUMENT_PARAMS, responses=s.DocumentSerializer,
    )  # fmt: skip
    def get(self, request: Request, student_id: str) -> Response:
        student = _student(request, student_id)
        template, locale = _document_args(request)
        with service_errors():
            html = lifecycle.id_card(
                actor=_actor(request), student=student, template_key=template, locale=locale
            )
        return Response({"html": html})


class PromotionPreviewView(StudentsBaseView):
    permission_classes = [HasTenantPermission({"POST": "students.student.promote"})]

    @extend_schema(
        tags=TAGS, summary="Preview a promotion (suggestions; nothing changes)",
        request=s.PromotionSerializer, responses=s.PromotionRowSerializer(many=True),
    )  # fmt: skip
    def post(self, request: Request) -> Response:
        v = _valid(s.PromotionSerializer, request.data)
        with service_errors():
            rows = lifecycle.promotion_preview(actor=_actor(request), **v)
        return Response(s.PromotionRowSerializer(rows, many=True).data)


class PromotionApplyView(StudentsBaseView):
    permission_classes = [HasTenantPermission({"POST": "students.student.promote"})]

    @extend_schema(
        tags=TAGS, summary="Apply confirmed promotion decisions (one transaction)",
        request=s.PromotionApplySerializer, responses=s.PromotionResultSerializer,
    )  # fmt: skip
    def post(self, request: Request) -> Response:
        v = _valid(s.PromotionApplySerializer, request.data)
        v.pop("rule_key", None)
        decisions = {str(k): str(a) for k, a in v.pop("decisions").items()}
        with service_errors():
            counts = lifecycle.apply_promotion(
                actor=_actor(request), decisions=decisions, request=request._request, **v
            )
        return Response(counts)


# --------------------------------------------------------------------------- imports (M6)
IMPORT_CODES = ("students.student.import", "staff.profile.manage")


def _require_kind_permission(view: Any, request: Request, kind_code: str) -> str:
    """The kind's permission through the same class as everywhere else (incl. MFA and the
    step-up the code requires), held in some scope of the tenant; services re-check the exact
    institution."""
    from rest_framework.exceptions import PermissionDenied as Forbidden

    try:
        code = imports.kind(kind_code).permission
    except ValidationError:
        raise DRFValidationError({"kind": "Unknown import kind."}) from None
    check = HasTenantPermission(code)()
    if not check.has_permission(request, view):
        raise Forbidden(getattr(check, "message", None))
    return code


def _job(request: Request, job_id: str) -> ImportJob:
    """The job when the member started it, or holds its kind's permission in its institution."""
    try:
        row = ImportJob.objects.filter(pk=job_id).first()
    except (ValueError, ValidationError):
        row = None
    if row is None:
        raise NotFound()
    actor = _actor(request)
    if row.created_by != actor.pk:
        visible_institution(actor, imports.kind(row.kind).permission, row.institution_id)
    return row


class ImportsView(StudentsBaseView):
    permission_classes = [HasTenantAnyPermission(*IMPORT_CODES)]

    @extend_schema(
        tags=TAGS, summary="My imports (newest first)", responses=s.ImportJobSerializer(many=True)
    )
    def get(self, request: Request) -> Response:
        rows = ImportJob.objects.filter(created_by=_actor(request).pk).order_by("-created_at")
        return Response(s.ImportJobSerializer(rows[:100], many=True).data)

    @extend_schema(
        tags=TAGS, summary="Start an import (queues the dry run)",
        request=s.ImportCreateSerializer, responses={201: s.ImportJobSerializer},
    )  # fmt: skip
    def post(self, request: Request) -> Response:
        v = _valid(s.ImportCreateSerializer, request.data)
        code = _require_kind_permission(self, request, v["kind"])
        inst = visible_institution(_actor(request), code, v["institution"])
        with service_errors():
            row = imports.start(
                actor=_actor(request), institution=inst, kind_code=v["kind"], file_id=v["file"],
                mapping=v["mapping"], options=v["options"], request=request._request,
            )  # fmt: skip
        return Response(s.ImportJobSerializer(row).data, status=status.HTTP_201_CREATED)


class ImportDetailView(StudentsBaseView):
    permission_classes = [HasTenantAnyPermission(*IMPORT_CODES)]

    @extend_schema(
        tags=TAGS, summary="An import with its row report", responses=s.ImportJobDetailSerializer
    )
    def get(self, request: Request, job_id: str) -> Response:
        return Response(s.ImportJobDetailSerializer(_job(request, job_id)).data)


class ImportApplyView(StudentsBaseView):
    permission_classes = [HasTenantAnyPermission(*IMPORT_CODES)]

    @extend_schema(
        tags=TAGS, summary="Apply a validated import (each row atomic)",
        request=None, responses=s.ImportJobSerializer,
    )  # fmt: skip
    def post(self, request: Request, job_id: str) -> Response:
        row = _job(request, job_id)
        _require_kind_permission(self, request, row.kind)
        with service_errors():
            row = imports.apply(actor=_actor(request), job=row, request=request._request)
        return Response(s.ImportJobSerializer(row).data)


class ImportReportView(StudentsBaseView):
    permission_classes = [HasTenantAnyPermission(*IMPORT_CODES)]

    @extend_schema(
        tags=TAGS, summary="The row report as CSV (formulas neutralised)",
        responses={(200, "text/csv"): OpenApiTypes.STR},
    )  # fmt: skip
    def get(self, request: Request, job_id: str) -> HttpResponse:
        row = _job(request, job_id)
        response = HttpResponse(imports.report_csv(row), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="import-{row.pk}.csv"'
        return response
