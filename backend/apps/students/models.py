"""Students, guardians and enrollments (Phase 7 M1; ADR-068).

* ``Student``: one learner of one institution; numbered from a Studio sequence (ADR-074 Q1);
  ``extra`` holds Studio custom fields (entity ``students.student``). An optional membership
  is the portal login (ADR-069).
* ``Guardian``: a person responsible for one or more students, tenant-wide (a guardian may have
  children in several institutions of the organisation); ``extra`` for custom fields (entity
  ``students.guardian``). Phone-only guardians have no login until Phase 14 (ADR-074 Q2).
* ``StudentGuardian``: the N-N link with the relation and its flags.
* ``Enrollment``: a student in a leaf unit of the Phase 6 tree for an academic year; at most one
  active enrollment per student and year.

Every table is tenant-owned (standard RLS) with composite tenant/institution keys
(``students.0002``).
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
        db_constraint=False,  # enforced by composite tenant keys (students.0002)
    )


class Student(TenantScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        TRANSFERRED = "transferred", "Transferred"
        ALUMNI = "alumni", "Alumni"
        WITHDRAWN = "withdrawn", "Withdrawn"

    institution = _fk("tenancy.Institution")
    number = models.CharField(max_length=64)
    name = models.CharField(max_length=160)
    name_i18n = models.JSONField(default=dict, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=32, blank=True)
    email = models.EmailField(max_length=254, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    photo_file_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    membership = _fk("tenancy.Membership", null=True)
    source_application_id = models.UUIDField(null=True, blank=True)
    extra = models.JSONField(default=dict, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "students_student"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "institution", "number"], name="students_student_number_unique"
            ),
            models.UniqueConstraint(
                fields=["tenant", "institution", "id"], name="students_student_tenant_key"
            ),
            # Guardian links reference a student by (tenant, id).
            models.UniqueConstraint(fields=["tenant", "id"], name="students_student_tenant_id_key"),
            models.UniqueConstraint(
                fields=["tenant", "source_application_id"],
                condition=models.Q(source_application_id__isnull=False),
                name="students_student_one_per_application",
            ),
            models.UniqueConstraint(
                fields=["tenant", "membership"],
                condition=models.Q(membership__isnull=False),
                name="students_student_one_per_membership",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "institution", "status"])]

    def __str__(self) -> str:
        return self.number or self.name


class Guardian(TenantScopedModel):
    name = models.CharField(max_length=160)
    name_i18n = models.JSONField(default=dict, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(max_length=254, blank=True)
    membership = _fk("tenancy.Membership", null=True)
    extra = models.JSONField(default=dict, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "students_guardian"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "id"], name="students_guardian_tenant_key"),
            models.UniqueConstraint(
                fields=["tenant", "membership"],
                condition=models.Q(membership__isnull=False),
                name="students_guardian_one_per_membership",
            ),
            models.CheckConstraint(
                condition=~models.Q(phone="") | ~models.Q(email=""),
                name="students_guardian_contact",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "phone"]),
            models.Index(fields=["tenant", "email"]),
        ]

    def __str__(self) -> str:
        return self.name


class StudentGuardian(TenantScopedModel):
    student = _fk("students.Student", related_name="guardian_links")
    guardian = _fk("students.Guardian", related_name="student_links")
    relation = models.CharField(max_length=32)
    is_primary = models.BooleanField(default=False)
    can_pickup = models.BooleanField(default=True)
    receives_notices = models.BooleanField(default=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "students_studentguardian"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "student", "guardian"], name="students_link_unique"
            ),
            models.UniqueConstraint(
                fields=["tenant", "student"],
                condition=models.Q(is_primary=True),
                name="students_link_one_primary",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student_id}:{self.guardian_id}"


class Enrollment(TenantScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PROMOTED = "promoted", "Promoted"
        REPEATED = "repeated", "Repeated"
        TRANSFERRED = "transferred", "Transferred"
        COMPLETED = "completed", "Completed"
        WITHDRAWN = "withdrawn", "Withdrawn"

    institution = _fk("tenancy.Institution")
    student = _fk("students.Student", related_name="enrollments")
    year = _fk("academics.AcademicYear")
    unit = _fk("academics.Unit")
    roll_number = models.CharField(max_length=16, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "students_enrollment"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "student", "year"],
                condition=models.Q(status="active"),
                name="students_enrollment_one_active",
            ),
            models.UniqueConstraint(
                fields=["tenant", "unit", "roll_number"],
                condition=models.Q(status="active") & ~models.Q(roll_number=""),
                name="students_enrollment_roll_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(end_date__isnull=True)
                | models.Q(end_date__gte=models.F("start_date")),
                name="students_enrollment_dates",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "unit", "status"])]

    def __str__(self) -> str:
        return f"{self.student_id}@{self.unit_id}"


class TransferCertificate(TenantScopedModel):
    """A transfer certificate issued when a student leaves (Phase 7 M5). The printable
    document is rendered from a Studio template on demand (ADR-056, ADR-074 Q5)."""

    institution = _fk("tenancy.Institution")
    student = _fk("students.Student", related_name="transfer_certificates")
    number = models.CharField(max_length=64)
    reason = models.CharField(max_length=300)
    destination = models.CharField(max_length=200, blank=True)
    issued_on = models.DateField()

    class Meta(TenantScopedModel.Meta):
        db_table = "students_transfercertificate"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "institution", "number"], name="students_tc_number_unique"
            ),
        ]

    def __str__(self) -> str:
        return self.number
