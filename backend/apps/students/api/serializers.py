"""Students API serializers (Phase 7 M2)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.students.models import (
    Enrollment,
    Guardian,
    ImportJob,
    Student,
    StudentGuardian,
    TransferCertificate,
)


class EnrollmentSerializer(serializers.ModelSerializer[Enrollment]):
    unit_name = serializers.CharField(source="unit.name", read_only=True)
    year_name = serializers.CharField(source="year.name", read_only=True)

    class Meta:
        model = Enrollment
        fields = [
            "id", "year", "year_name", "unit", "unit_name", "roll_number", "status", "start_date",
            "end_date",
        ]  # fmt: skip
        read_only_fields = fields


class GuardianSerializer(serializers.ModelSerializer[Guardian]):
    has_login = serializers.SerializerMethodField()

    class Meta:
        model = Guardian
        fields = ["id", "name", "name_i18n", "phone", "email", "has_login"]
        read_only_fields = fields

    def get_has_login(self, obj: Guardian) -> bool:
        return obj.membership_id is not None


class GuardianLinkSerializer(serializers.ModelSerializer[StudentGuardian]):
    guardian = GuardianSerializer(read_only=True)

    class Meta:
        model = StudentGuardian
        fields = ["id", "guardian", "relation", "is_primary", "can_pickup", "receives_notices"]
        read_only_fields = fields


class StudentSerializer(serializers.ModelSerializer[Student]):
    class Meta:
        model = Student
        fields = [
            "id", "institution", "number", "name", "name_i18n", "date_of_birth", "gender",
            "email", "phone", "status",
        ]  # fmt: skip
        read_only_fields = fields


class StudentDetailSerializer(StudentSerializer):
    extra = serializers.DictField(read_only=True)
    enrollments = EnrollmentSerializer(many=True, read_only=True)
    guardians = GuardianLinkSerializer(many=True, read_only=True)
    relation = serializers.CharField(read_only=True)

    class Meta(StudentSerializer.Meta):
        fields = [*StudentSerializer.Meta.fields, "extra", "enrollments", "guardians", "relation"]
        read_only_fields = fields


class PersonValuesSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=160, required=False)
    name_i18n = serializers.DictField(child=serializers.CharField(), required=False)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    gender = serializers.CharField(max_length=32, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True)


class StudentCreateSerializer(serializers.Serializer[Any]):
    institution = serializers.UUIDField()
    values = PersonValuesSerializer()
    extra = serializers.DictField(required=False, default=dict)
    number = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class StudentUpdateSerializer(serializers.Serializer[Any]):
    values = PersonValuesSerializer(required=False)
    extra = serializers.DictField(required=False)


class GuardianLinkCreateSerializer(serializers.Serializer[Any]):
    guardian = serializers.UUIDField(required=False)
    values = PersonValuesSerializer(required=False)
    extra = serializers.DictField(required=False, default=dict)
    relation = serializers.CharField(max_length=32, default="guardian")
    is_primary = serializers.BooleanField(default=False)
    can_pickup = serializers.BooleanField(default=True)
    receives_notices = serializers.BooleanField(default=True)


class EnrollmentCreateSerializer(serializers.Serializer[Any]):
    year = serializers.UUIDField()
    unit = serializers.UUIDField()
    roll_number = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
    start_date = serializers.DateField(required=False, allow_null=True, default=None)


class GuardianMergeSerializer(serializers.Serializer[Any]):
    keep = serializers.UUIDField()
    duplicate = serializers.UUIDField()


class FromApplicationSerializer(serializers.Serializer[Any]):
    application = serializers.UUIDField()


# --------------------------------------------------------------------------- lifecycle (M5)
class MoveSerializer(serializers.Serializer[Any]):
    unit = serializers.UUIDField()
    roll_number = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")


class WithdrawSerializer(serializers.Serializer[Any]):
    reason = serializers.CharField(max_length=300)
    on = serializers.DateField(required=False, allow_null=True, default=None)


class TransferCertificateCreateSerializer(WithdrawSerializer):
    destination = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    number = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class TransferCertificateSerializer(serializers.ModelSerializer[TransferCertificate]):
    class Meta:
        model = TransferCertificate
        fields = ["id", "student", "number", "reason", "destination", "issued_on"]
        read_only_fields = fields


class PromotionSerializer(serializers.Serializer[Any]):
    year_from = serializers.UUIDField()
    unit_from = serializers.UUIDField()
    year_to = serializers.UUIDField()
    unit_to = serializers.UUIDField(required=False, allow_null=True, default=None)
    rule_key = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class PromotionApplySerializer(PromotionSerializer):
    decisions = serializers.DictField(
        child=serializers.ChoiceField(choices=["promote", "repeat", "complete"])
    )


class PromotionRowSerializer(serializers.Serializer[Any]):
    student = serializers.UUIDField()
    name = serializers.CharField()
    number = serializers.CharField()
    roll_number = serializers.CharField()
    suggestion = serializers.CharField()
    note = serializers.CharField()


class PromotionResultSerializer(serializers.Serializer[Any]):
    promote = serializers.IntegerField()
    repeat = serializers.IntegerField()
    complete = serializers.IntegerField()


class DocumentSerializer(serializers.Serializer[Any]):
    html = serializers.CharField()


# --------------------------------------------------------------------------- imports (M6)
class ImportCreateSerializer(serializers.Serializer[Any]):
    institution = serializers.UUIDField()
    kind = serializers.CharField(max_length=32)
    file = serializers.UUIDField()
    mapping = serializers.DictField(child=serializers.CharField(max_length=80))
    options = serializers.DictField(required=False, default=dict)


class ImportRowSerializer(serializers.Serializer[Any]):
    row = serializers.IntegerField()
    ok = serializers.BooleanField()
    errors = serializers.DictField(child=serializers.CharField())  # type: ignore[assignment]  # field name shadows a DRF attribute
    id = serializers.CharField(allow_null=True)


class ImportJobSerializer(serializers.ModelSerializer[ImportJob]):
    class Meta:
        model = ImportJob
        fields = [
            "id", "institution", "kind", "file_id", "mapping", "options", "status", "total_rows",
            "ok_rows", "error_rows", "error", "created_at", "finished_at",
        ]  # fmt: skip
        read_only_fields = fields


class ImportJobDetailSerializer(ImportJobSerializer):
    report = ImportRowSerializer(many=True, read_only=True)

    class Meta(ImportJobSerializer.Meta):
        fields = [*ImportJobSerializer.Meta.fields, "report"]
        read_only_fields = fields
