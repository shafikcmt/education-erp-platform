"""Academics API serializers (Phase 6 M2)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.academics.models import AcademicYear, Offering, OfferingTeacher, Subject, Term, Unit

_CODE = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,31}$"


class SetupSerializer(serializers.Serializer[Any]):
    levels = serializers.ListField(child=serializers.CharField())
    level_labels = serializers.DictField(child=serializers.CharField())
    credit_based = serializers.BooleanField()
    semester_based = serializers.BooleanField()
    section_enabled = serializers.BooleanField()


class YearSerializer(serializers.ModelSerializer[AcademicYear]):
    class Meta:
        model = AcademicYear
        fields = [
            "id",
            "institution",
            "code",
            "name",
            "name_i18n",
            "start_date",
            "end_date",
            "status",
        ]
        read_only_fields = fields


class YearCreateSerializer(serializers.Serializer[Any]):
    institution = serializers.UUIDField()
    code = serializers.RegexField(_CODE)
    name = serializers.CharField(max_length=120)
    name_i18n = serializers.DictField(child=serializers.CharField(max_length=200), required=False)
    start_date = serializers.DateField()
    end_date = serializers.DateField()


class YearStatusSerializer(serializers.Serializer[Any]):
    status = serializers.ChoiceField(
        choices=[AcademicYear.Status.ACTIVE, AcademicYear.Status.CLOSED]
    )


class TermSerializer(serializers.ModelSerializer[Term]):
    class Meta:
        model = Term
        fields = [
            "id",
            "year",
            "kind",
            "code",
            "name",
            "name_i18n",
            "order",
            "start_date",
            "end_date",
        ]
        read_only_fields = fields


class TermCreateSerializer(serializers.Serializer[Any]):
    kind = serializers.ChoiceField(choices=Term.Kind.choices, required=False, default="term")
    code = serializers.RegexField(_CODE)
    name = serializers.CharField(max_length=120)
    name_i18n = serializers.DictField(child=serializers.CharField(max_length=200), required=False)
    order = serializers.IntegerField(min_value=1, max_value=20, required=False, default=1)
    start_date = serializers.DateField()
    end_date = serializers.DateField()


class UnitSerializer(serializers.ModelSerializer[Unit]):
    class Meta:
        model = Unit
        fields = [
            "id", "institution", "campus", "parent", "level_key", "code", "name", "name_i18n",
            "capacity", "order", "archived_at",
        ]  # fmt: skip
        read_only_fields = fields


class UnitCreateSerializer(serializers.Serializer[Any]):
    institution = serializers.UUIDField()
    level_key = serializers.CharField(max_length=40)
    code = serializers.RegexField(_CODE)
    name = serializers.CharField(max_length=120)
    name_i18n = serializers.DictField(child=serializers.CharField(max_length=200), required=False)
    parent = serializers.UUIDField(required=False, allow_null=True)  # type: ignore[assignment]  # field name shadows a DRF attribute
    campus = serializers.UUIDField(required=False, allow_null=True)
    capacity = serializers.IntegerField(
        min_value=1, max_value=100000, required=False, allow_null=True
    )
    order = serializers.IntegerField(min_value=0, max_value=1000, required=False, default=0)


class UnitUpdateSerializer(serializers.Serializer[Any]):
    code = serializers.RegexField(_CODE, required=False)
    name = serializers.CharField(max_length=120, required=False)
    name_i18n = serializers.DictField(child=serializers.CharField(max_length=200), required=False)
    capacity = serializers.IntegerField(
        min_value=1, max_value=100000, required=False, allow_null=True
    )
    order = serializers.IntegerField(min_value=0, max_value=1000, required=False)


class SubjectSerializer(serializers.ModelSerializer[Subject]):
    class Meta:
        model = Subject
        fields = [
            "id", "institution", "code", "name", "name_i18n", "subject_type", "credits",
            "archived_at",
        ]  # fmt: skip
        read_only_fields = fields


class SubjectCreateSerializer(serializers.Serializer[Any]):
    institution = serializers.UUIDField()
    code = serializers.RegexField(_CODE)
    name = serializers.CharField(max_length=160)
    name_i18n = serializers.DictField(child=serializers.CharField(max_length=200), required=False)
    subject_type = serializers.RegexField(r"^[a-z][a-z0-9_]{1,31}$", required=False, default="core")
    credits = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, required=False, allow_null=True
    )


class TeacherSerializer(serializers.ModelSerializer[OfferingTeacher]):
    class Meta:
        model = OfferingTeacher
        fields = ["id", "membership", "role"]
        read_only_fields = fields


class OfferingSerializer(serializers.ModelSerializer[Offering]):
    teachers = TeacherSerializer(many=True, read_only=True)

    class Meta:
        model = Offering
        fields = ["id", "year", "term", "unit", "subject", "credits", "teachers"]
        read_only_fields = fields


class OfferingCreateSerializer(serializers.Serializer[Any]):
    year = serializers.UUIDField()
    unit = serializers.UUIDField()
    subject = serializers.UUIDField()
    term = serializers.UUIDField(required=False, allow_null=True)
    credits = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, required=False, allow_null=True
    )


class TeacherAssignSerializer(serializers.Serializer[Any]):
    membership = serializers.UUIDField()
    role = serializers.ChoiceField(
        choices=OfferingTeacher.Role.choices, required=False, default="primary"
    )
