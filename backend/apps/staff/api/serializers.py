"""Staff API serializers (Phase 7 M3)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.staff.models import Department, Designation, StaffProfile, UnitAdvisor


class DepartmentSerializer(serializers.ModelSerializer[Department]):
    archived = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = ["id", "institution", "parent", "code", "name", "name_i18n", "kind", "archived"]
        read_only_fields = fields

    def get_archived(self, obj: Department) -> bool:
        return obj.archived_at is not None


class DesignationSerializer(serializers.ModelSerializer[Designation]):
    archived = serializers.SerializerMethodField()

    class Meta:
        model = Designation
        fields = ["id", "institution", "code", "name", "name_i18n", "archived"]
        read_only_fields = fields

    def get_archived(self, obj: Designation) -> bool:
        return obj.archived_at is not None


class StaffProfileSerializer(serializers.ModelSerializer[StaffProfile]):
    department_name = serializers.CharField(source="department.name", default="", read_only=True)
    designation_name = serializers.CharField(source="designation.name", default="", read_only=True)
    has_login = serializers.SerializerMethodField()

    class Meta:
        model = StaffProfile
        fields = [
            "id", "institution", "campus", "number", "name", "name_i18n", "gender", "email",
            "phone", "joining_date", "status", "employment_type", "department",
            "department_name", "designation", "designation_name", "has_login",
        ]  # fmt: skip
        read_only_fields = fields

    def get_has_login(self, obj: StaffProfile) -> bool:
        return obj.membership_id is not None


class AdvisorSerializer(serializers.ModelSerializer[UnitAdvisor]):
    unit_name = serializers.CharField(source="unit.name", read_only=True)
    year_name = serializers.CharField(source="year.name", read_only=True)
    staff_name = serializers.CharField(source="staff.name", read_only=True)

    class Meta:
        model = UnitAdvisor
        fields = [
            "id", "year", "year_name", "unit", "unit_name", "staff", "staff_name", "is_primary",
        ]  # fmt: skip
        read_only_fields = fields


class StaffProfileDetailSerializer(StaffProfileSerializer):
    extra = serializers.DictField(read_only=True)
    advising = AdvisorSerializer(many=True, read_only=True)
    relation = serializers.CharField(read_only=True)

    class Meta(StaffProfileSerializer.Meta):
        fields = [*StaffProfileSerializer.Meta.fields, "extra", "advising", "relation"]
        read_only_fields = fields


class DepartmentCreateSerializer(serializers.Serializer[Any]):
    institution = serializers.UUIDField()
    code = serializers.CharField(max_length=32)
    name = serializers.CharField(max_length=120)
    name_i18n = serializers.DictField(child=serializers.CharField(), required=False, default=dict)
    kind = serializers.ChoiceField(choices=Department.Kind.choices, default="academic")
    parent = serializers.UUIDField(required=False, allow_null=True, default=None)  # type: ignore[assignment]  # field name shadows a DRF attribute


class DepartmentUpdateSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=120, required=False)
    name_i18n = serializers.DictField(child=serializers.CharField(), required=False)
    kind = serializers.ChoiceField(choices=Department.Kind.choices, required=False)
    parent = serializers.UUIDField(required=False, allow_null=True)  # type: ignore[assignment]  # field name shadows a DRF attribute
    archived = serializers.BooleanField(required=False)


class DesignationCreateSerializer(serializers.Serializer[Any]):
    institution = serializers.UUIDField()
    code = serializers.CharField(max_length=32)
    name = serializers.CharField(max_length=120)
    name_i18n = serializers.DictField(child=serializers.CharField(), required=False, default=dict)


class DesignationUpdateSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=120, required=False)
    name_i18n = serializers.DictField(child=serializers.CharField(), required=False)
    archived = serializers.BooleanField(required=False)


class StaffValuesSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=160, required=False)
    name_i18n = serializers.DictField(child=serializers.CharField(), required=False)
    gender = serializers.CharField(max_length=32, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True)
    joining_date = serializers.DateField(required=False, allow_null=True)


class StaffLinksSerializer(serializers.Serializer[Any]):
    campus = serializers.UUIDField(required=False, allow_null=True)
    department = serializers.UUIDField(required=False, allow_null=True)
    designation = serializers.UUIDField(required=False, allow_null=True)
    membership = serializers.UUIDField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=StaffProfile.Status.choices, required=False)
    employment_type = serializers.ChoiceField(
        choices=StaffProfile.Employment.choices, required=False
    )


class StaffCreateSerializer(serializers.Serializer[Any]):
    institution = serializers.UUIDField()
    values = StaffValuesSerializer()
    extra = serializers.DictField(required=False, default=dict)
    number = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    links = StaffLinksSerializer(required=False, default=dict)


class StaffUpdateSerializer(serializers.Serializer[Any]):
    values = StaffValuesSerializer(required=False)
    extra = serializers.DictField(required=False)
    links = StaffLinksSerializer(required=False)


class AdvisorCreateSerializer(serializers.Serializer[Any]):
    year = serializers.UUIDField()
    unit = serializers.UUIDField()
    staff = serializers.UUIDField()
    is_primary = serializers.BooleanField(default=True)
