"""Attendance API serializers (Phase 8 M2)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.attendance.models import Register, Status


class RegisterSerializer(serializers.ModelSerializer[Register]):
    unit_name = serializers.CharField(source="unit.name", read_only=True)
    subject_name = serializers.CharField(source="offering.subject.name", default="", read_only=True)

    class Meta:
        model = Register
        fields = [
            "id", "institution", "campus", "year", "term", "unit", "unit_name", "date", "kind",
            "offering", "subject_name", "sequence", "state", "submitted_at", "locked_at",
            "version", "taken_by",
        ]  # fmt: skip
        read_only_fields = fields


class RosterEntrySerializer(serializers.Serializer[Any]):
    student_id = serializers.UUIDField()
    name = serializers.CharField()
    number = serializers.CharField()
    roll_number = serializers.CharField()
    status = serializers.ChoiceField(choices=Status.choices)
    late_minutes = serializers.IntegerField(allow_null=True)
    remark = serializers.CharField(allow_blank=True)
    status_source = serializers.ChoiceField(choices=["saved", "leave", "default"])
    on_leave = serializers.BooleanField()


class RegisterDetailSerializer(serializers.Serializer[Any]):
    register = RegisterSerializer()
    roster = RosterEntrySerializer(many=True)
    can_mark = serializers.BooleanField()
    can_manage = serializers.BooleanField()
    outside_window = serializers.BooleanField()


class DueSerializer(serializers.Serializer[Any]):
    kind = serializers.ChoiceField(choices=Register.Kind.choices)
    institution = serializers.UUIDField(source="institution_id")
    unit = serializers.UUIDField(source="unit_id")
    unit_name = serializers.CharField()
    offering = serializers.UUIDField(source="offering_id", allow_null=True)
    subject_name = serializers.CharField(allow_blank=True)
    register = RegisterSerializer(allow_null=True)


class OpenSerializer(serializers.Serializer[Any]):
    kind = serializers.ChoiceField(choices=Register.Kind.choices)
    date = serializers.DateField()
    unit = serializers.UUIDField(required=False, allow_null=True)
    offering = serializers.UUIDField(required=False, allow_null=True)
    sequence = serializers.IntegerField(min_value=1, max_value=20, default=1)


class EntrySerializer(serializers.Serializer[Any]):
    student = serializers.UUIDField()
    status = serializers.ChoiceField(choices=Status.choices)
    late_minutes = serializers.IntegerField(
        min_value=0, max_value=600, required=False, allow_null=True
    )
    remark = serializers.CharField(max_length=160, required=False, allow_blank=True)


class SaveSerializer(serializers.Serializer[Any]):
    version = serializers.IntegerField(min_value=1)
    entries = serializers.ListField(child=EntrySerializer(), allow_empty=False, max_length=2000)
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True)


class SubmitSerializer(serializers.Serializer[Any]):
    version = serializers.IntegerField(min_value=1)


class UnlockSerializer(serializers.Serializer[Any]):
    reason = serializers.CharField(max_length=300)
