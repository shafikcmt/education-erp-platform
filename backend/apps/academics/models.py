"""Academic structure (Phase 6 M1; ADR-063).

* ``AcademicYear`` and ``Term`` are the time dimension.
* ``Unit`` is one generic tree for the organisational levels of an institution (class/section,
  faculty/department/program, marhala/jamaat, program/batch). A unit's ``level_key`` is one of
  the institution's effective ``customization.structure_levels``; the service layer checks the
  order (a child sits exactly one level below its parent).
* ``Subject`` covers subjects, courses and kitabs; credits are used when the institution is
  credit-based.
* ``Offering`` puts a subject in a unit for a year (and term), with teachers (memberships;
  Phase 7 links staff profiles to the same membership).

Every table is tenant-owned (standard RLS). References are composite ``(tenant_id,
institution_id, …)`` keys in the database (``academics.0002``), so no row can point into another
tenant or another institution.
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
        db_constraint=False,  # enforced by composite tenant keys (academics.0002)
    )


class AcademicYear(TenantScopedModel):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"

    institution = _fk("tenancy.Institution")
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    name_i18n = models.JSONField(default=dict, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PLANNED)

    class Meta(TenantScopedModel.Meta):
        db_table = "academics_academicyear"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "institution", "code"], name="academics_year_code_unique"
            ),
            models.UniqueConstraint(
                fields=["tenant", "institution"],
                condition=models.Q(status="active"),
                name="academics_year_one_active",
            ),
            models.UniqueConstraint(
                fields=["tenant", "institution", "id"], name="academics_year_tenant_key"
            ),
            models.CheckConstraint(
                condition=models.Q(start_date__lt=models.F("end_date")),
                name="academics_year_dates",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Term(TenantScopedModel):
    class Kind(models.TextChoices):
        TERM = "term", "Term"
        SEMESTER = "semester", "Semester"
        TRIMESTER = "trimester", "Trimester"
        QUARTER = "quarter", "Quarter"

    institution = _fk("tenancy.Institution")
    year = _fk("academics.AcademicYear", related_name="terms")
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.TERM)
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    name_i18n = models.JSONField(default=dict, blank=True)
    order = models.PositiveSmallIntegerField(default=1)
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta(TenantScopedModel.Meta):
        db_table = "academics_term"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "year", "code"], name="academics_term_code"),
            models.UniqueConstraint(
                fields=["tenant", "institution", "id"], name="academics_term_tenant_key"
            ),
            # An offering's term must belong to the offering's year (academics.0002).
            models.UniqueConstraint(
                fields=["tenant", "year", "id"], name="academics_term_year_key"
            ),
            models.CheckConstraint(
                condition=models.Q(start_date__lt=models.F("end_date")),
                name="academics_term_dates",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Unit(TenantScopedModel):
    institution = _fk("tenancy.Institution")
    campus = _fk("tenancy.Campus", null=True)
    parent = _fk("academics.Unit", null=True, related_name="children")
    level_key = models.CharField(max_length=40)
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    name_i18n = models.JSONField(default=dict, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "academics_unit"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "institution", "parent", "code"],
                nulls_distinct=False,
                name="academics_unit_code_unique",
            ),
            models.UniqueConstraint(
                fields=["tenant", "institution", "id"], name="academics_unit_tenant_key"
            ),
            models.CheckConstraint(
                condition=~models.Q(parent=models.F("id")), name="academics_unit_not_own_parent"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.level_key} {self.code}"


class Subject(TenantScopedModel):
    institution = _fk("tenancy.Institution")
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=160)
    name_i18n = models.JSONField(default=dict, blank=True)
    subject_type = models.CharField(max_length=32, default="core")
    credits = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "academics_subject"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "institution", "code"], name="academics_subject_code_unique"
            ),
            models.UniqueConstraint(
                fields=["tenant", "institution", "id"], name="academics_subject_tenant_key"
            ),
            models.CheckConstraint(
                condition=models.Q(credits__isnull=True) | models.Q(credits__gt=0),
                name="academics_subject_credits_positive",
            ),
        ]

    def __str__(self) -> str:
        return self.code


class Offering(TenantScopedModel):
    institution = _fk("tenancy.Institution")
    year = _fk("academics.AcademicYear")
    term = _fk("academics.Term", null=True)
    unit = _fk("academics.Unit")
    subject = _fk("academics.Subject")
    credits = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "academics_offering"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "year", "term", "unit", "subject"],
                nulls_distinct=False,
                name="academics_offering_unique",
            ),
            models.UniqueConstraint(fields=["tenant", "id"], name="academics_offering_tenant_key"),
            models.CheckConstraint(
                condition=models.Q(credits__isnull=True) | models.Q(credits__gt=0),
                name="academics_offering_credits_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"offering {self.pk}"


class OfferingTeacher(TenantScopedModel):
    class Role(models.TextChoices):
        PRIMARY = "primary", "Primary"
        ASSISTANT = "assistant", "Assistant"

    offering = _fk("academics.Offering", related_name="teachers")
    membership = _fk("tenancy.Membership")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.PRIMARY)

    class Meta(TenantScopedModel.Meta):
        db_table = "academics_offeringteacher"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "offering", "membership"], name="academics_teacher_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.membership_id} teaches {self.offering_id}"
