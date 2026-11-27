"""Portal serializers (Phase 7 M8)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


class CurrentEnrollmentSerializer(serializers.Serializer[Any]):
    unit = serializers.UUIDField()
    unit_name = serializers.CharField()
    year = serializers.UUIDField()
    year_name = serializers.CharField()
    roll_number = serializers.CharField()


class ChildSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    name = serializers.CharField()
    number = serializers.CharField()
    institution = serializers.UUIDField()
    status = serializers.CharField()
    relation = serializers.CharField()
    current = CurrentEnrollmentSerializer(allow_null=True)


class LessonSerializer(serializers.Serializer[Any]):
    weekday = serializers.IntegerField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    period_name = serializers.CharField()
    subject_name = serializers.CharField()
    room_code = serializers.CharField()


class ChildDetailSerializer(ChildSerializer):
    date_of_birth = serializers.DateField(allow_null=True)
    timetable = LessonSerializer(many=True)
