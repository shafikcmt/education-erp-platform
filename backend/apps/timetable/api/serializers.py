"""Timetable API serializers (Phase 7 M7)."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.timetable.models import BellSchedule, Period, Room, Slot


class PeriodSerializer(serializers.ModelSerializer[Period]):
    class Meta:
        model = Period
        fields = ["id", "order", "name", "start_time", "end_time", "is_break"]
        read_only_fields = fields


class ScheduleSerializer(serializers.ModelSerializer[BellSchedule]):
    periods = serializers.SerializerMethodField()

    class Meta:
        model = BellSchedule
        fields = ["id", "institution", "code", "name", "periods"]
        read_only_fields = fields

    @extend_schema_field(PeriodSerializer(many=True))
    def get_periods(self, obj: BellSchedule) -> list[dict[str, Any]]:
        rows = Period.objects.filter(schedule=obj).order_by("order")
        return list(PeriodSerializer(rows, many=True).data)


class RoomSerializer(serializers.ModelSerializer[Room]):
    class Meta:
        model = Room
        fields = ["id", "institution", "campus", "code", "name", "capacity"]
        read_only_fields = fields


class SlotSerializer(serializers.ModelSerializer[Slot]):
    unit_name = serializers.CharField(source="unit.name", read_only=True)
    period_name = serializers.CharField(source="period.name", read_only=True)
    start_time = serializers.TimeField(source="period.start_time", read_only=True)
    end_time = serializers.TimeField(source="period.end_time", read_only=True)
    subject_name = serializers.CharField(source="offering.subject.name", read_only=True)
    room_code = serializers.CharField(source="room.code", default="", read_only=True)

    class Meta:
        model = Slot
        fields = [
            "id", "year", "term", "unit", "unit_name", "weekday", "period", "period_name",
            "start_time", "end_time", "offering", "subject_name", "teacher", "room", "room_code",
        ]  # fmt: skip
        read_only_fields = fields


class ScheduleCreateSerializer(serializers.Serializer[Any]):
    institution = serializers.UUIDField()
    code = serializers.CharField(max_length=32)
    name = serializers.CharField(max_length=120)


class PeriodCreateSerializer(serializers.Serializer[Any]):
    order = serializers.IntegerField(min_value=1, max_value=30)
    name = serializers.CharField(max_length=60)
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    is_break = serializers.BooleanField(default=False)


class RoomCreateSerializer(serializers.Serializer[Any]):
    institution = serializers.UUIDField()
    code = serializers.CharField(max_length=32)
    name = serializers.CharField(max_length=120)
    campus = serializers.UUIDField(required=False, allow_null=True, default=None)
    capacity = serializers.IntegerField(required=False, allow_null=True, default=None)


class SlotCreateSerializer(serializers.Serializer[Any]):
    offering = serializers.UUIDField()
    weekday = serializers.IntegerField(min_value=1, max_value=7)
    period = serializers.UUIDField()
    teacher = serializers.UUIDField(required=False, allow_null=True)
    room = serializers.UUIDField(required=False, allow_null=True, default=None)
