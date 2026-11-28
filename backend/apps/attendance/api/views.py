"""Attendance API (Phase 8 M2; ADR-077). Tenant host only, module ``attendance``.

Teachers see and mark the registers of the units they advise and the offerings they teach;
``attendance.record.view`` shows an institution's (or a campus's) registers and
``attendance.record.manage`` marks any of them. Hidden registers answer 404. Services re-check
everything in the exact scope; edits past the edit window and unlocking also need MFA and a
fresh step-up here.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from apps.attendance import selectors, services
from apps.attendance.api import serializers as s
from apps.attendance.models import Register
from apps.identity import errors
from apps.identity import session_state as state
from apps.identity.api.utils import service_errors
from apps.identity.models import User
from apps.tenancy.api.permissions import HasTenantAnyPermission, visible_institution
from apps.tenancy.api.views_tenant import TenantView

TAGS = ["attendance"]
MARK, VIEW, MANAGE = selectors.MARK, selectors.VIEW, selectors.MANAGE


def _actor(request: Request) -> User:
    assert isinstance(request.user, User)  # noqa: S101 - permission classes guarantee it
    return request.user


def _valid(serializer: Any, data: Any) -> dict[str, Any]:
    form = serializer(data=data)
    form.is_valid(raise_exception=True)
    return dict(form.validated_data)


def _register(request: Request, register_id: str) -> Register:
    try:
        row = selectors.visible_register(_actor(request), register_id)
    except (ValueError, ValidationError):
        row = None
    if row is None:
        raise NotFound()
    return row


def _manager_checks(request: Request) -> None:
    """MFA and a fresh step-up for the manager-only paths (``attendance.record.manage``)."""
    if not state.mfa_verified(request._request):
        raise errors.MfaRequired()
    if not state.step_up_fresh(request._request):
        raise errors.StepUpRequired()


def _detail(actor: User, row: Register) -> dict[str, Any]:
    return {
        "register": row,
        "roster": selectors.roster(row),
        "can_mark": selectors.can_mark(actor, row),
        "can_manage": selectors.holds_at(actor, MANAGE, row.institution_id, row.campus_id),
        "outside_window": services.outside_window(row),
    }


class AttendanceView(TenantView):
    module_code = "attendance"


class DueView(AttendanceView):
    permission_classes = [HasTenantAnyPermission(MARK, MANAGE)]

    @extend_schema(
        tags=TAGS, summary="Registers I am expected to take on a date (default today)",
        parameters=[OpenApiParameter("date", str)], responses=s.DueSerializer(many=True),
    )  # fmt: skip
    def get(self, request: Request) -> Response:
        form = s.OpenSerializer().fields["date"]
        raw = request.query_params.get("date")
        on = form.to_internal_value(raw) if raw else services.today()
        rows = selectors.due_for(_actor(request), on)
        return Response(s.DueSerializer(rows, many=True).data)


class RegistersView(AttendanceView):
    permission_classes = [HasTenantAnyPermission(VIEW, MARK, MANAGE)]

    @extend_schema(
        tags=TAGS, summary="Registers of an institution on a date",
        parameters=[
            OpenApiParameter("institution", str, required=True),
            OpenApiParameter("date", str), OpenApiParameter("unit", str),
        ],
        responses=s.RegisterSerializer(many=True),
    )  # fmt: skip
    def get(self, request: Request) -> Response:
        actor, params = _actor(request), request.query_params
        inst = None
        for code in (VIEW, MANAGE, MARK):
            try:
                inst = visible_institution(actor, code, params.get("institution"))
                break
            except NotFound:
                continue
        if inst is None:
            raise NotFound()
        rows = selectors.registers_in(actor, inst.pk).select_related("unit", "offering__subject")
        try:
            if day := params.get("date"):
                rows = rows.filter(date=s.OpenSerializer().fields["date"].to_internal_value(day))
            if unit := params.get("unit"):
                rows = rows.filter(unit_id=unit)
        except (ValueError, ValidationError):
            raise NotFound() from None
        rows = rows.order_by("-date", "unit__code", "kind", "sequence")[:500]
        return Response(s.RegisterSerializer(rows, many=True).data)

    @extend_schema(
        tags=TAGS, summary="Open (or return) a daily or period register",
        request=s.OpenSerializer, responses={201: s.RegisterDetailSerializer},
    )  # fmt: skip
    def post(self, request: Request) -> Response:
        v = _valid(s.OpenSerializer, request.data)
        with service_errors():
            row = services.open_register(
                actor=_actor(request), kind=v["kind"], on=v["date"], unit=v.get("unit"),
                offering=v.get("offering"), sequence=v["sequence"], request=request._request,
            )  # fmt: skip
        data = s.RegisterDetailSerializer(_detail(_actor(request), row)).data
        return Response(data, status=status.HTTP_201_CREATED)


class RegisterView(AttendanceView):
    permission_classes = [HasTenantAnyPermission(VIEW, MARK, MANAGE)]

    @extend_schema(tags=TAGS, summary="A register with its roster",
                   responses=s.RegisterDetailSerializer)  # fmt: skip
    def get(self, request: Request, register_id: str) -> Response:
        row = _register(request, register_id)
        return Response(s.RegisterDetailSerializer(_detail(_actor(request), row)).data)


class RegisterSaveView(AttendanceView):
    permission_classes = [HasTenantAnyPermission(MARK, MANAGE)]

    @extend_schema(
        tags=TAGS, summary="Save students' statuses (optimistic version)",
        request=s.SaveSerializer, responses=s.RegisterDetailSerializer,
    )  # fmt: skip
    def post(self, request: Request, register_id: str) -> Response:
        row = _register(request, register_id)
        v = _valid(s.SaveSerializer, request.data)
        if services.outside_window(row):
            _manager_checks(request)
        entries = [{**e, "student": str(e["student"])} for e in v["entries"]]
        with service_errors():
            row = services.save(
                actor=_actor(request), register=row, version=v["version"], entries=entries,
                reason=v.get("reason", ""), request=request._request,
            )  # fmt: skip
        return Response(s.RegisterDetailSerializer(_detail(_actor(request), row)).data)


class RegisterSubmitView(AttendanceView):
    permission_classes = [HasTenantAnyPermission(MARK, MANAGE)]

    @extend_schema(tags=TAGS, summary="Submit a register", request=s.SubmitSerializer,
                   responses=s.RegisterDetailSerializer)  # fmt: skip
    def post(self, request: Request, register_id: str) -> Response:
        row = _register(request, register_id)
        v = _valid(s.SubmitSerializer, request.data)
        with service_errors():
            row = services.submit(
                actor=_actor(request), register=row, version=v["version"],
                request=request._request,
            )  # fmt: skip
        return Response(s.RegisterDetailSerializer(_detail(_actor(request), row)).data)


class RegisterUnlockView(AttendanceView):
    permission_classes = [HasTenantAnyPermission(MANAGE)]

    @extend_schema(tags=TAGS, summary="Unlock a locked register (manager, reason, step-up)",
                   request=s.UnlockSerializer, responses=s.RegisterDetailSerializer)  # fmt: skip
    def post(self, request: Request, register_id: str) -> Response:
        row = _register(request, register_id)
        v = _valid(s.UnlockSerializer, request.data)
        _manager_checks(request)
        with service_errors():
            row = services.unlock(
                actor=_actor(request), register=row, reason=v["reason"], request=request._request
            )
        return Response(s.RegisterDetailSerializer(_detail(_actor(request), row)).data)


# --------------------------------------------------------------------------- leave (M3)
LEAVE_REQUEST, LEAVE_REVIEW = "attendance.leave.request", "attendance.leave.review"


def _leave(request: Request, leave_id: str) -> Any:
    from apps.attendance import leave

    try:
        row = leave.visible_leave(_actor(request)).filter(pk=leave_id).first()
    except (ValueError, ValidationError):
        row = None
    if row is None:
        raise NotFound()
    return row


class LeavesView(AttendanceView):
    permission_classes = [HasTenantAnyPermission(LEAVE_REQUEST, LEAVE_REVIEW)]

    @extend_schema(
        tags=TAGS, summary="Leave requests I made, of my children or myself, or that I review",
        parameters=[OpenApiParameter("state", str)], responses=s.LeaveSerializer(many=True),
    )  # fmt: skip
    def get(self, request: Request) -> Response:
        from apps.attendance import leave

        rows = leave.visible_leave(_actor(request)).select_related("student", "staff")
        if state_filter := request.query_params.get("state"):
            rows = rows.filter(state=state_filter)
        rows = rows.order_by("-start_date", "-created_at")[:500]
        return Response(s.LeaveSerializer(rows, many=True).data)

    @extend_schema(tags=TAGS, summary="Request leave", request=s.LeaveCreateSerializer,
                   responses={201: s.LeaveSerializer})  # fmt: skip
    def post(self, request: Request) -> Response:
        from apps.attendance import leave

        v = _valid(s.LeaveCreateSerializer, request.data)
        with service_errors():
            row = leave.request_leave(
                actor=_actor(request), student=v.get("student"), staff=v.get("staff"),
                start_date=v["start_date"], end_date=v["end_date"], half_day=v["half_day"],
                reason=v["reason"], request=request._request,
            )  # fmt: skip
        return Response(s.LeaveSerializer(row).data, status=status.HTTP_201_CREATED)


class LeaveView(AttendanceView):
    permission_classes = [HasTenantAnyPermission(LEAVE_REQUEST, LEAVE_REVIEW)]

    @extend_schema(tags=TAGS, summary="A leave request", responses=s.LeaveSerializer)
    def get(self, request: Request, leave_id: str) -> Response:
        return Response(s.LeaveSerializer(_leave(request, leave_id)).data)


class LeaveDecideView(AttendanceView):
    permission_classes = [HasTenantAnyPermission(LEAVE_REVIEW)]

    @extend_schema(tags=TAGS, summary="Approve or reject a leave request",
                   request=s.LeaveDecisionSerializer, responses=s.LeaveSerializer)  # fmt: skip
    def post(self, request: Request, leave_id: str) -> Response:
        from apps.attendance import leave

        row = _leave(request, leave_id)
        v = _valid(s.LeaveDecisionSerializer, request.data)
        with service_errors():
            row = leave.decide(
                actor=_actor(request), leave=row, approve=v["approve"],
                note=v.get("note", ""), request=request._request,
            )  # fmt: skip
        return Response(s.LeaveSerializer(row).data)


class LeaveCancelView(AttendanceView):
    permission_classes = [HasTenantAnyPermission(LEAVE_REQUEST, LEAVE_REVIEW)]

    @extend_schema(tags=TAGS, summary="Cancel a pending or future leave request", request=None,
                   responses=s.LeaveSerializer)  # fmt: skip
    def post(self, request: Request, leave_id: str) -> Response:
        from apps.attendance import leave

        row = _leave(request, leave_id)
        with service_errors():
            row = leave.cancel(actor=_actor(request), leave=row, request=request._request)
        return Response(s.LeaveSerializer(row).data)


# --------------------------------------------------------------------------- staff (M4)
STAFF_MARK, STAFF_VIEW, STAFF_OWN = (
    "attendance.staff.mark",
    "attendance.staff.view",
    "staff.profile.view_own",
)


def _staff_register(actor: User, institution_id: Any, on: Any, campus: Any = None) -> Any:
    from apps.attendance import staff_register

    return {
        "institution": institution_id,
        "date": on,
        "outside_window": staff_register.outside_window(institution_id, on),
        "can_mark": staff_register.staff_in_scope(actor, institution_id, STAFF_MARK).exists(),
        "rows": staff_register.register(actor, institution_id, on, campus),
    }


class StaffRegisterView(AttendanceView):
    permission_classes = [HasTenantAnyPermission(STAFF_VIEW, STAFF_MARK)]

    @extend_schema(
        tags=TAGS, summary="The staff register of an institution on a date",
        parameters=[OpenApiParameter("institution", str, required=True),
                    OpenApiParameter("date", str), OpenApiParameter("campus", str)],
        responses=s.StaffRegisterSerializer,
    )  # fmt: skip
    def get(self, request: Request) -> Response:
        from apps.attendance import staff_register

        actor, params = _actor(request), request.query_params
        try:
            import uuid

            inst = uuid.UUID(params.get("institution") or "")
            if not staff_register.can_see(actor, inst):
                raise NotFound()
            raw = params.get("date")
            on = (
                s.OpenSerializer().fields["date"].to_internal_value(raw)
                if raw
                else services.today()
            )
            campus = uuid.UUID(params["campus"]) if params.get("campus") else None
            data = _staff_register(actor, inst, on, campus)
        except (ValueError, ValidationError):
            raise NotFound() from None
        return Response(s.StaffRegisterSerializer(data).data)


class StaffRegisterSaveView(AttendanceView):
    permission_classes = [HasTenantAnyPermission(STAFF_MARK)]

    @extend_schema(tags=TAGS, summary="Save the staff register (step-up past the edit window)",
                   request=s.StaffSaveSerializer, responses=s.StaffRegisterSerializer)  # fmt: skip
    def post(self, request: Request) -> Response:
        from apps.attendance import staff_register

        v = _valid(s.StaffSaveSerializer, request.data)
        actor = _actor(request)
        if not staff_register.can_see(actor, v["institution"]):
            raise NotFound()
        if staff_register.outside_window(v["institution"], v["date"]) and not state.step_up_fresh(
            request._request
        ):
            raise errors.StepUpRequired()
        entries = [{**e, "staff": str(e["staff"])} for e in v["entries"]]
        with service_errors():
            staff_register.save(
                actor=actor, institution=v["institution"], on=v["date"], entries=entries,
                reason=v.get("reason", ""), request=request._request,
            )  # fmt: skip
        return Response(s.StaffRegisterSerializer(
            _staff_register(actor, v["institution"], v["date"])).data)  # fmt: skip


class MyStaffDaysView(AttendanceView):
    permission_classes = [HasTenantAnyPermission(STAFF_OWN)]

    @extend_schema(
        tags=TAGS, summary="My own staff attendance in a month (YYYY-MM, default this month)",
        parameters=[OpenApiParameter("month", str)], responses=s.StaffDaySerializer(many=True),
    )  # fmt: skip
    def get(self, request: Request) -> Response:
        import datetime as dt

        from apps.attendance import staff_register

        raw = request.query_params.get("month") or services.today().strftime("%Y-%m")
        try:
            start = dt.date.fromisoformat(f"{raw}-01")
        except ValueError:
            raise NotFound() from None
        end = (start.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(1)
        rows = staff_register.my_days(_actor(request), start, end)
        return Response(s.StaffDaySerializer(rows, many=True).data)
