"""Admissions (Phase 6 M4; ADR-065).

* ``Inquiry``: a lead (contact, interest, source, follow-up).
* ``Cycle``: an admission round of an institution for an academic year, bound to a published
  Studio form (entity ``admissions.application``) and optionally a workflow, a merit rule and a
  numbering sequence; ``CycleTarget`` are the units admitted to, with capacity.
* ``Application``: one applicant for one target of a cycle. Core values the platform uses are
  columns; the remaining core values are in ``core`` and custom values in ``extra`` (validated
  against the form). Students are created from accepted applications in Phase 7
  (``ADMISSIONS_ACCEPTED_HANDLERS``).

All tables are tenant-owned (standard RLS) with composite tenant/institution keys
(``admissions.0002``).
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
        db_constraint=False,  # composite tenant keys (admissions.0002)
    )


class Inquiry(TenantScopedModel):
    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        CONVERTED = "converted", "Converted"
        CLOSED = "closed", "Closed"

    institution = _fk("tenancy.Institution")
    name = models.CharField(max_length=160)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(max_length=254, blank=True)
    interest = models.CharField(max_length=200, blank=True)
    source = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)
    assigned_to = _fk("tenancy.Membership", null=True)
    follow_up_on = models.DateField(null=True, blank=True)
    notes = models.TextField(max_length=2000, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "admissions_inquiry"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(phone="", email=""), name="admissions_inquiry_contact"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Cycle(TenantScopedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"
        ARCHIVED = "archived", "Archived"

    institution = _fk("tenancy.Institution")
    year = _fk("academics.AcademicYear")
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=160)
    name_i18n = models.JSONField(default=dict, blank=True)
    opens_on = models.DateField()
    closes_on = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    form_key = models.CharField(max_length=64)
    workflow_key = models.CharField(max_length=64, blank=True)
    merit_rule_key = models.CharField(max_length=64, blank=True)
    numbering_key = models.CharField(max_length=64, blank=True)
    fee_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    fee_currency = models.CharField(max_length=3, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "admissions_cycle"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "institution", "code"], name="admissions_cycle_code_unique"
            ),
            models.UniqueConstraint(
                fields=["tenant", "institution", "id"], name="admissions_cycle_tenant_key"
            ),
            models.CheckConstraint(
                condition=models.Q(opens_on__lte=models.F("closes_on")),
                name="admissions_cycle_dates",
            ),
            models.CheckConstraint(
                condition=models.Q(fee_amount__isnull=True)
                | (models.Q(fee_amount__gte=0) & models.Q(fee_currency__regex=r"^[A-Z]{3}$")),
                name="admissions_cycle_fee",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class CycleTarget(TenantScopedModel):
    institution = _fk("tenancy.Institution")
    cycle = _fk("admissions.Cycle", related_name="targets")
    unit = _fk("academics.Unit")
    capacity = models.PositiveIntegerField()

    class Meta(TenantScopedModel.Meta):
        db_table = "admissions_cycletarget"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "cycle", "unit"], name="admissions_target_unique"
            ),
            models.UniqueConstraint(fields=["tenant", "cycle", "id"], name="admissions_target_key"),
            models.CheckConstraint(
                condition=models.Q(capacity__gt=0), name="admissions_target_capacity"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.cycle_id}:{self.unit_id}"


class Application(TenantScopedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under review"
        TEST_SCHEDULED = "test_scheduled", "Test scheduled"
        EVALUATED = "evaluated", "Evaluated"
        OFFERED = "offered", "Offered"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        REJECTED = "rejected", "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn"

    class Source(models.TextChoices):
        STAFF = "staff", "Entered by staff"
        PUBLIC = "public", "Public form"

    institution = _fk("tenancy.Institution")
    cycle = _fk("admissions.Cycle", related_name="applications")
    target = _fk("admissions.CycleTarget")
    number = models.CharField(max_length=64, blank=True)
    applicant_name = models.CharField(max_length=160)
    applicant_email = models.EmailField(max_length=254, blank=True)
    applicant_phone = models.CharField(max_length=32, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    core = models.JSONField(default=dict, blank=True)
    extra = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.STAFF)
    workflow_instance_id = models.UUIDField(null=True, blank=True)
    score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    merit_rank = models.PositiveIntegerField(null=True, blank=True)
    decision_note = models.CharField(max_length=500, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "admissions_application"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "cycle", "number"],
                condition=~models.Q(number=""),
                name="admissions_application_number_unique",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "cycle", "status"])]

    def __str__(self) -> str:
        return self.number or str(self.pk)
