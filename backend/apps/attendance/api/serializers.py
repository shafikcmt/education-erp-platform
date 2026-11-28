"""Attendance API serializers (Phase 8 M2)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.attendance.models import LeaveRequest, Register, Status


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


class LeaveSerializer(serializers.ModelSerializer[LeaveRequest]):
    student_name = serializers.CharField(source="student.name", default="", read_only=True)
    staff_name = serializers.CharField(source="staff.name", default="", read_only=True)

    class Meta:
        model = LeaveRequest
        fields = [
            "id", "institution", "student", "student_name", "staff", "staff_name", "start_date",
            "end_date", "half_day", "reason", "state", "requested_by", "decided_by",
            "decided_at", "decision_note", "workflow_instance_id", "created_at",
        ]  # fmt: skip
        read_only_fields = fields


class LeaveCreateSerializer(serializers.Serializer[Any]):
    student = serializers.UUIDField(required=False, allow_null=True)
    staff = serializers.UUIDField(required=False, allow_null=True)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    half_day = serializers.BooleanField(default=False)
    reason = serializers.CharField(max_length=500)


class LeaveDecisionSerializer(serializers.Serializer[Any]):
    approve = serializers.BooleanField()
    note = serializers.CharField(max_length=300, required=False, allow_blank=True)


class StaffRowSerializer(serializers.Serializer[Any]):
    staff_id = serializers.UUIDField()
    name = serializers.CharField()
    number = serializers.CharField()
    campus = serializers.UUIDField(allow_null=True)
    status = serializers.ChoiceField(choices=Status.choices)
    check_in = serializers.TimeField(allow_null=True)
    check_out = serializers.TimeField(allow_null=True)
    remark = serializers.CharField(allow_blank=True)
    status_source = serializers.ChoiceField(choices=["saved", "leave", "default"])
    on_leave = serializers.BooleanField()


class StaffRegisterSerializer(serializers.Serializer[Any]):
    institution = serializers.UUIDField()
    date = serializers.DateField()
    outside_window = serializers.BooleanField()
    can_mark = serializers.BooleanField()
    rows = StaffRowSerializer(many=True)


class StaffEntrySerializer(serializers.Serializer[Any]):
    staff = serializers.UUIDField()
    status = serializers.ChoiceField(choices=Status.choices)
    check_in = serializers.TimeField(required=False, allow_null=True)
    check_out = serializers.TimeField(required=False, allow_null=True)
    remark = serializers.CharField(max_length=160, required=False, allow_blank=True)


class StaffSaveSerializer(serializers.Serializer[Any]):
    institution = serializers.UUIDField()
    date = serializers.DateField()
    entries = serializers.ListField(child=StaffEntrySerializer(), allow_empty=False,
                                    max_length=2000)  # fmt: skip
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True)


class StaffDaySerializer(serializers.Serializer[Any]):
    date = serializers.DateField()
    status = serializers.ChoiceField(choices=Status.choices)
    check_in = serializers.TimeField(allow_null=True)
    check_out = serializers.TimeField(allow_null=True)


class DailyStatusSerializer(serializers.Serializer[Any]):
    unit = serializers.UUIDField()
    unit_name = serializers.CharField()
    register = serializers.UUIDField(allow_null=True)
    state = serializers.ChoiceField(choices=["open", "submitted", "locked", "missing"])
    marked = serializers.IntegerField()
    absent = serializers.IntegerField()


class GridRowSerializer(serializers.Serializer[Any]):
    student_id = serializers.UUIDField()
    name = serializers.CharField()
    number = serializers.CharField()
    roll_number = serializers.CharField()
    cells = serializers.DictField(child=serializers.CharField())
    percent = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)


class UnitMonthSerializer(serializers.Serializer[Any]):
    unit = serializers.UUIDField()
    unit_name = serializers.CharField()
    month = serializers.CharField()
    dates = serializers.ListField(child=serializers.CharField())
    rows = GridRowSerializer(many=True)


class StudentSummarySerializer(serializers.Serializer[Any]):
    student_id = serializers.UUIDField()
    name = serializers.CharField()
    number = serializers.CharField()
    unit = serializers.CharField()
    roll_number = serializers.CharField()
    attended_days = serializers.IntegerField()
    absent_days = serializers.IntegerField()
    late_days = serializers.IntegerField()
    not_counted_days = serializers.IntegerField()
    percent = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)


class StaffGridRowSerializer(serializers.Serializer[Any]):
    staff_id = serializers.UUIDField()
    name = serializers.CharField()
    number = serializers.CharField()
    cells = serializers.DictField(child=serializers.CharField())
    absent = serializers.IntegerField()


class StaffMonthSerializer(serializers.Serializer[Any]):
    month = serializers.CharField()
    dates = serializers.ListField(child=serializers.CharField())
    rows = StaffGridRowSerializer(many=True)


class RegisterDocumentSerializer(serializers.Serializer[Any]):
    html = serializers.CharField()


class PortalAttendanceSerializer(serializers.Serializer[Any]):
    student = serializers.UUIDField()
    month = serializers.CharField()
    days = serializers.DictField(child=serializers.CharField())
    percent = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    absent_days = serializers.IntegerField()
    late_days = serializers.IntegerField()
    flagged = serializers.BooleanField()
    leave = LeaveSerializer(many=True)
