"""Departments, designations, staff profiles and class-teacher advisors (Phase 7 M3; ADR-070).

* ``Department``: per institution, with an optional parent; academic or administrative.
* ``Designation``: per institution (Lecturer, Ustad, Accountant, ...).
* ``StaffProfile``: one person working at one institution, with or without a login (support
  staff often have none). Teaching is keyed by memberships (ADR-063), so a teacher's profile
  links the same membership and nothing in ``academics`` changes. ``extra`` holds Studio custom
  fields (entity ``staff.profile``); HR-sensitive fields are masked by their view permission.
* ``UnitAdvisor``: a class teacher (advisor) of a unit for an academic year. Advisors see the
  students of their units (``students.student.view_assigned``, through the setting
  ``STUDENTS_ASSIGNED_UNITS``).

Every table is tenant-owned (standard RLS) with composite tenant/institution keys (``staff.0002``).
"""

from __future__ import annotations

from django.db import models

from apps.core.tenancy.models import TenantScopedModel


def _fk(to: str, *, null: bool = False, related_name: str = "+") -> models.ForeignKey:  # type: ignore[type-arg]
    return models.ForeignKey(
        to,
        on_delete=models.PROTECT,
        related_name=related_name,
        null=null,
        blank=null,
        db_constraint=False,  # enforced by composite tenant keys (staff.0002)
    )


class Department(TenantScopedModel):
    class Kind(models.TextChoices):
        ACADEMIC = "academic", "Academic"
        ADMINISTRATIVE = "administrative", "Administrative"

    institution = _fk("tenancy.Institution")
    parent = _fk("staff.Department", null=True, related_name="children")
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    name_i18n = models.JSONField(default=dict, blank=True)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.ACADEMIC)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "staff_department"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "institution", "code"], name="staff_department_code_unique"
            ),
            models.UniqueConstraint(
                fields=["tenant", "institution", "id"], name="staff_department_tenant_key"
            ),
        ]

    def __str__(self) -> str:
        return self.code


class Designation(TenantScopedModel):
    institution = _fk("tenancy.Institution")
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    name_i18n = models.JSONField(default=dict, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "staff_designation"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "institution", "code"], name="staff_designation_code_unique"
            ),
            models.UniqueConstraint(
                fields=["tenant", "institution", "id"], name="staff_designation_tenant_key"
            ),
        ]

    def __str__(self) -> str:
        return self.code


class StaffProfile(TenantScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ON_LEAVE = "on_leave", "On leave"
        INACTIVE = "inactive", "Inactive"
        LEFT = "left", "Left"

    class Employment(models.TextChoices):
        PERMANENT = "permanent", "Permanent"
        CONTRACT = "contract", "Contract"
        PART_TIME = "part_time", "Part-time"
        VISITING = "visiting", "Visiting"
        VOLUNTEER = "volunteer", "Volunteer"

    institution = _fk("tenancy.Institution")
    campus = _fk("tenancy.Campus", null=True)
    number = models.CharField(max_length=64)
    name = models.CharField(max_length=160)
    name_i18n = models.JSONField(default=dict, blank=True)
    gender = models.CharField(max_length=32, blank=True)
    email = models.EmailField(max_length=254, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    joining_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    employment_type = models.CharField(
        max_length=16, choices=Employment.choices, default=Employment.PERMANENT
    )
    department = _fk("staff.Department", null=True)
    designation = _fk("staff.Designation", null=True)
    membership = _fk("tenancy.Membership", null=True)
    extra = models.JSONField(default=dict, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "staff_profile"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "institution", "number"], name="staff_profile_number_unique"
            ),
            models.UniqueConstraint(
                fields=["tenant", "institution", "id"], name="staff_profile_tenant_key"
            ),
            # One profile per login and institution (a person may work at two institutions).
            models.UniqueConstraint(
                fields=["tenant", "institution", "membership"],
                condition=models.Q(membership__isnull=False),
                name="staff_profile_one_per_membership",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "institution", "status"])]

    def __str__(self) -> str:
        return self.number or self.name


class UnitAdvisor(TenantScopedModel):
    institution = _fk("tenancy.Institution")
    year = _fk("academics.AcademicYear")
    unit = _fk("academics.Unit")
    staff = _fk("staff.StaffProfile", related_name="advised_units")
    is_primary = models.BooleanField(default=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "staff_unitadvisor"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "year", "unit", "staff"], name="staff_advisor_unique"
            ),
            models.UniqueConstraint(
                fields=["tenant", "year", "unit"],
                condition=models.Q(is_primary=True),
                name="staff_advisor_one_primary",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.staff_id}@{self.unit_id}"
