"""Timetable API (Phase 7 M7; ADR-071). Tenant host only, module ``timetable``.

Staff (timetable and structure view in the institution) see every unit's, teacher's and room's
timetable; guardians and students only their children's or their own units; everyone with the
view code sees the lessons they teach (``timetable/my/``). Anything else answers 404. Writes
need ``timetable.timetable.manage``, re-checked in the exact institution by the services.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from apps.identity.api.utils import get_or_404, service_errors
from apps.identity.models import User
from apps.tenancy.api.permissions import HasTenantPermission, visible_institution
from apps.tenancy.api.views_tenant import TenantView
from apps.timetable import selectors, services
from apps.timetable.api import serializers as s
from apps.timetable.models import BellSchedule, Room, Slot

TAGS = ["timetable"]
VIEW, MANAGE = selectors.VIEW, services.MANAGE
INSTITUTION = OpenApiParameter("institution", str, required=True)


def _actor(request: Request) -> User:
    assert isinstance(request.user, User)  # noqa: S101 - permission classes guarantee it
    return request.user


def _valid(serializer: Any, data: Any) -> dict[str, Any]:
    form = serializer(data=data)
    form.is_valid(raise_exception=True)
    return dict(form.validated_data)


def _staff_institution(request: Request, institution_id: Any) -> Any:
    from apps.tenancy.models import Institution

    try:
        inst = Institution.objects.filter(pk=institution_id).first() if institution_id else None
    except (ValueError, ValidationError):
        inst = None
    if inst is None or not selectors.staff_view(_actor(request), inst.pk):
        raise NotFound()
    return inst


class TimetableView(TenantView):
    module_code = "timetable"


class SchedulesView(TimetableView):
    permission_classes = [HasTenantPermission({"GET": VIEW, "POST": MANAGE})]

    @extend_schema(
        tags=TAGS, summary="Bell schedules with their periods", parameters=[INSTITUTION],
        responses=s.ScheduleSerializer(many=True),
    )  # fmt: skip
    def get(self, request: Request) -> Response:
        inst = _staff_institution(request, request.query_params.get("institution"))
        rows = BellSchedule.objects.filter(institution=inst, archived_at__isnull=True)
        return Response(s.ScheduleSerializer(rows.order_by("code"), many=True).data)

    @extend_schema(
        tags=TAGS, summary="Create a bell schedule", request=s.ScheduleCreateSerializer,
        responses={201: s.ScheduleSerializer},
    )  # fmt: skip
    def post(self, request: Request) -> Response:
        v = _valid(s.ScheduleCreateSerializer, request.data)
        inst = visible_institution(_actor(request), MANAGE, v.pop("institution"))
        with service_errors():
            row = services.create_schedule(
                actor=_actor(request), institution=inst, request=request._request, **v
            )
        return Response(s.ScheduleSerializer(row).data, status=status.HTTP_201_CREATED)


class SchedulePeriodsView(TimetableView):
    permission_classes = [HasTenantPermission({"POST": MANAGE})]

    @extend_schema(
        tags=TAGS, summary="Add a period to a bell schedule", request=s.PeriodCreateSerializer,
        responses={201: s.PeriodSerializer},
    )  # fmt: skip
    def post(self, request: Request, schedule_id: str) -> Response:
        schedule = get_or_404(BellSchedule.objects.all(), schedule_id)
        visible_institution(_actor(request), MANAGE, schedule.institution_id)
        v = _valid(s.PeriodCreateSerializer, request.data)
        with service_errors():
            row = services.add_period(
                actor=_actor(request), schedule=schedule, request=request._request, **v
            )
        return Response(s.PeriodSerializer(row).data, status=status.HTTP_201_CREATED)


class RoomsView(TimetableView):
    permission_classes = [HasTenantPermission({"GET": VIEW, "POST": MANAGE})]

    @extend_schema(
        tags=TAGS, summary="Rooms of an institution", parameters=[INSTITUTION],
        responses=s.RoomSerializer(many=True),
    )  # fmt: skip
    def get(self, request: Request) -> Response:
        inst = _staff_institution(request, request.query_params.get("institution"))
        rows = Room.objects.filter(institution=inst, archived_at__isnull=True).order_by("code")
        return Response(s.RoomSerializer(rows, many=True).data)

    @extend_schema(
        tags=TAGS, summary="Create a room", request=s.RoomCreateSerializer,
        responses={201: s.RoomSerializer},
    )  # fmt: skip
    def post(self, request: Request) -> Response:
        v = _valid(s.RoomCreateSerializer, request.data)
        inst = visible_institution(_actor(request), MANAGE, v.pop("institution"))
        with service_errors():
            row = services.create_room(
                actor=_actor(request), institution=inst, request=request._request, **v
            )
        return Response(s.RoomSerializer(row).data, status=status.HTTP_201_CREATED)


class SlotsView(TimetableView):
    permission_classes = [HasTenantPermission({"GET": VIEW, "POST": MANAGE})]

    @extend_schema(
        tags=TAGS,
        summary="A unit's, room's or teacher's timetable",
        parameters=[
            OpenApiParameter("unit", str), OpenApiParameter("room", str),
            OpenApiParameter("teacher", str, description="Membership id"),
            OpenApiParameter("year", str),
        ],
        responses=s.SlotSerializer(many=True),
    )  # fmt: skip
    def get(self, request: Request) -> Response:
        from apps.academics.models import Unit

        params, actor = request.query_params, _actor(request)
        rows = selectors.slots()
        try:
            if year := params.get("year"):
                rows = rows.filter(year_id=uuid.UUID(year))
            if unit_id := params.get("unit"):
                unit = Unit.objects.filter(pk=unit_id).first()
                if unit is None:
                    raise NotFound()
                if not selectors.staff_view(actor, unit.institution_id) and (
                    unit.pk not in selectors.portal_units(actor)
                ):
                    raise NotFound()
                rows = rows.filter(unit=unit)
            elif room_id := params.get("room"):
                room = get_or_404(Room.objects.all(), room_id)
                _staff_institution(request, room.institution_id)
                rows = rows.filter(room=room)
            elif teacher := params.get("teacher"):
                rows = rows.filter(teacher_id=uuid.UUID(teacher))
                institutions = set(rows.values_list("institution_id", flat=True))
                if not all(selectors.staff_view(actor, i) for i in institutions):
                    raise NotFound()
            else:
                raise NotFound()
            data = s.SlotSerializer(rows[:500], many=True).data
        except (ValueError, ValidationError):
            raise NotFound() from None
        return Response(data)

    @extend_schema(
        tags=TAGS, summary="Add a weekly lesson (clashes are refused)",
        request=s.SlotCreateSerializer, responses={201: s.SlotSerializer},
    )  # fmt: skip
    def post(self, request: Request) -> Response:
        from apps.academics.models import Offering

        v = _valid(s.SlotCreateSerializer, request.data)
        offering = get_or_404(Offering.objects.all(), v["offering"])
        visible_institution(_actor(request), MANAGE, offering.institution_id)
        with service_errors():
            row = services.create_slot(
                actor=_actor(request), offering=offering, weekday=v["weekday"],
                period=v["period"], teacher=v.get("teacher", "default"), room=v["room"],
                request=request._request,
            )  # fmt: skip
        return Response(s.SlotSerializer(row).data, status=status.HTTP_201_CREATED)


class SlotDetailView(TimetableView):
    permission_classes = [HasTenantPermission({"DELETE": MANAGE})]

    @extend_schema(tags=TAGS, summary="Remove a lesson", responses={204: None})
    def delete(self, request: Request, slot_id: str) -> Response:
        row = get_or_404(Slot.objects.all(), slot_id)
        visible_institution(_actor(request), MANAGE, row.institution_id)
        with service_errors():
            services.delete_slot(actor=_actor(request), slot=row, request=request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyTimetableView(TimetableView):
    permission_classes = [HasTenantPermission({"GET": VIEW})]

    @extend_schema(tags=TAGS, summary="The lessons I teach", responses=s.SlotSerializer(many=True))
    def get(self, request: Request) -> Response:
        rows = selectors.my_slots(_actor(request))[:500]
        return Response(s.SlotSerializer(rows, many=True).data)
