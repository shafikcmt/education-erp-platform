"""Admissions API serializers (Phase 6 M4)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.admissions.models import (
    Application,
    Cycle,
    CycleTarget,
    Inquiry,
    MeritList,
    Test,
    TestAssignment,
)

_CODE = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,31}$"
_KEY = r"^[a-z][a-z0-9_]{1,63}$"


class InquirySerializer(serializers.ModelSerializer[Inquiry]):
    class Meta:
        model = Inquiry
        fields = [
            "id", "institution", "name", "phone", "email", "interest", "source", "status",
            "assigned_to", "follow_up_on", "notes", "created_at",
        ]  # fmt: skip
        read_only_fields = fields


class InquiryWriteSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=160, required=False)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    email = serializers.EmailField(max_length=254, required=False, allow_blank=True)
    interest = serializers.CharField(max_length=200, required=False, allow_blank=True)
    source = serializers.CharField(max_length=32, required=False, allow_blank=True)  # type: ignore[assignment]  # field name shadows a DRF attribute
    status = serializers.ChoiceField(choices=Inquiry.Status.choices, required=False)
    assigned_to = serializers.UUIDField(required=False, allow_null=True)
    follow_up_on = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class InquiryCreateSerializer(InquiryWriteSerializer):
    institution = serializers.UUIDField()
    name = serializers.CharField(max_length=160)


class TargetSerializer(serializers.ModelSerializer[CycleTarget]):
    class Meta:
        model = CycleTarget
        fields = ["id", "unit", "capacity"]
        read_only_fields = fields


class CycleSerializer(serializers.ModelSerializer[Cycle]):
    targets = TargetSerializer(many=True, read_only=True)

    class Meta:
        model = Cycle
        fields = [
            "id", "institution", "year", "code", "name", "name_i18n", "opens_on", "closes_on",
            "status", "form_key", "workflow_key", "merit_rule_key", "numbering_key", "fee_amount",
            "fee_currency", "targets",
        ]  # fmt: skip
        read_only_fields = fields


class CycleCreateSerializer(serializers.Serializer[Any]):
    institution = serializers.UUIDField()
    year = serializers.UUIDField()
    code = serializers.RegexField(_CODE)
    name = serializers.CharField(max_length=160)
    name_i18n = serializers.DictField(child=serializers.CharField(max_length=200), required=False)
    opens_on = serializers.DateField()
    closes_on = serializers.DateField()
    form_key = serializers.RegexField(_KEY)
    workflow_key = serializers.RegexField(_KEY, required=False, allow_blank=True, default="")
    merit_rule_key = serializers.RegexField(_KEY, required=False, allow_blank=True, default="")
    numbering_key = serializers.RegexField(_KEY, required=False, allow_blank=True, default="")
    fee_amount = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=0, required=False, allow_null=True
    )
    fee_currency = serializers.RegexField(
        r"^[A-Z]{3}$", required=False, allow_blank=True, default=""
    )


class TargetCreateSerializer(serializers.Serializer[Any]):
    unit = serializers.UUIDField()
    capacity = serializers.IntegerField(min_value=1, max_value=100000)


class CycleStatusSerializer(serializers.Serializer[Any]):
    status = serializers.ChoiceField(choices=Cycle.Status.choices)


class ApplicationSerializer(serializers.ModelSerializer[Application]):
    class Meta:
        model = Application
        fields = [
            "id", "cycle", "target", "number", "applicant_name", "applicant_email",
            "applicant_phone", "date_of_birth", "core", "extra", "status", "source",
            "workflow_instance_id", "score", "merit_rank", "decision_note", "submitted_at",
            "decided_at", "responded_at",
        ]  # fmt: skip
        read_only_fields = fields


class ApplicationCreateSerializer(serializers.Serializer[Any]):
    cycle = serializers.UUIDField()
    target = serializers.UUIDField()
    values = serializers.DictField()


class DecisionSerializer(serializers.Serializer[Any]):
    decision = serializers.ChoiceField(
        choices=[Application.Status.OFFERED, Application.Status.REJECTED]
    )
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class OfferResponseSerializer(serializers.Serializer[Any]):
    accept = serializers.BooleanField()


# --------------------------------------------------------------------------- tests and merit (M6)
class TestSerializer(serializers.ModelSerializer[Test]):
    seated = serializers.IntegerField(read_only=True)

    class Meta:
        model = Test
        fields = ["id", "cycle", "name", "starts_at", "venue", "capacity", "max_score", "seated"]
        read_only_fields = fields


class TestCreateSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=160)
    starts_at = serializers.DateTimeField()
    venue = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    capacity = serializers.IntegerField(min_value=1)
    max_score = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal("0.01"))


class TestSeatSerializer(serializers.ModelSerializer[TestAssignment]):
    application_number = serializers.CharField(source="application.number", read_only=True)
    applicant_name = serializers.CharField(source="application.applicant_name", read_only=True)

    class Meta:
        model = TestAssignment
        fields = [
            "id", "test", "application", "application_number", "applicant_name", "seat", "score",
            "absent", "scored_at",
        ]  # fmt: skip
        read_only_fields = fields


class TestSeatCreateSerializer(serializers.Serializer[Any]):
    application = serializers.UUIDField()


class ScoreSerializer(serializers.Serializer[Any]):
    score = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=Decimal(0), allow_null=True
    )
    absent = serializers.BooleanField(required=False, default=False)


class RankedSerializer(serializers.Serializer[Any]):
    application = serializers.UUIDField()
    number = serializers.CharField()
    applicant_name = serializers.CharField(required=False)
    score = serializers.CharField()
    total = serializers.CharField()
    rank = serializers.IntegerField()
    status = serializers.CharField()


class MeritListSerializer(serializers.ModelSerializer[MeritList]):
    ranking = RankedSerializer(many=True)

    class Meta:
        model = MeritList
        fields = ["id", "target", "version", "rule_key", "published_at", "ranking"]
        read_only_fields = fields


class MeritSerializer(serializers.Serializer[Any]):
    preview = RankedSerializer(many=True)
    published = MeritListSerializer(allow_null=True)
