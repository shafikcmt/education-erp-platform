"""Attendance registers, records, staff records and leave requests (Phase 8 M1; ADR-076).

* ``Register``: one attendance register (the plan's "session"): a unit on a date, either the
  unit's ``daily`` register or a ``period`` register of an offering (``sequence`` numbers
  several lectures of the same offering on one day). One daily register per unit and date and
  one period register per offering, date and sequence: partial unique constraints, so
  concurrent writers can't create a duplicate. ``version`` is the optimistic-concurrency
  counter of the whole register (ADR-077). ``slot_ref`` optionally names the timetable slot
  (by id only: ``timetable`` is not a dependency of ``attendance``).
* ``Record``: one student's status in a register. ``date`` and ``institution`` are copied from
  the register and kept equal to it by a composite key on ``(register, date)``, so reports
  and a later monthly partitioning need no join (ADR-080).
* ``StaffRecord``: one staff member's daily status (plan §5).
* ``LeaveRequest``: a student's or a staff member's leave for a date range (plan §6). The
  approval runs through a Phase 5 workflow (M3); the instance is referenced by id.

Statuses are fixed categories the engine computes with (present, absent, late, excused,
leave); tenants rename them through Studio terminology (``attendance.status.<code>``), never
add new ones. Every table is tenant-owned with standard RLS and composite tenant/institution
keys (``attendance.0002``).
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
        db_constraint=False,  # enforced by composite tenant keys (attendance.0002)
    )


class Status(models.TextChoices):
    PRESENT = "present", "Present"
    ABSENT = "absent", "Absent"
    LATE = "late", "Late"
    EXCUSED = "excused", "Excused"
    LEAVE = "leave", "Leave"


# Counted as attended; not counted at all (neither for nor against the student).
ATTENDED = frozenset({Status.PRESENT, Status.LATE})
NOT_COUNTED = frozenset({Status.EXCUSED, Status.LEAVE})

_STATUS_VALUES = [s.value for s in Status]


class Register(TenantScopedModel):
    class Kind(models.TextChoices):
        DAILY = "daily", "Daily"
        PERIOD = "period", "Period"

    class State(models.TextChoices):
        OPEN = "open", "Open"
        SUBMITTED = "submitted", "Submitted"
        LOCKED = "locked", "Locked"

    institution = _fk("tenancy.Institution")
    campus = _fk("tenancy.Campus", null=True)
    year = _fk("academics.AcademicYear")
    term = _fk("academics.Term", null=True)
    unit = _fk("academics.Unit")
    date = models.DateField()
    kind = models.CharField(max_length=16, choices=Kind.choices)
    offering = _fk("academics.Offering", null=True)
    sequence = models.PositiveSmallIntegerField(default=1)
    slot_ref = models.UUIDField(null=True, blank=True)
    taken_by = _fk("tenancy.Membership", null=True)
    state = models.CharField(max_length=16, choices=State.choices, default=State.OPEN)
    submitted_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta(TenantScopedModel.Meta):
        db_table = "attendance_register"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "unit", "date"],
                condition=models.Q(kind="daily"),
                name="attendance_register_one_daily",
            ),
            models.UniqueConstraint(
                fields=["tenant", "offering", "date", "sequence"],
                condition=models.Q(kind="period"),
                name="attendance_register_one_period",
            ),
            models.UniqueConstraint(
                fields=["tenant", "institution", "id"], name="attendance_register_tenant_key"
            ),
            models.UniqueConstraint(
                fields=["tenant", "institution", "id", "date"],
                name="attendance_register_date_key",
            ),
            models.CheckConstraint(
                condition=(models.Q(kind="daily") & models.Q(offering__isnull=True))
                | (models.Q(kind="period") & models.Q(offering__isnull=False)),
                name="attendance_register_kind_offering",
            ),
            models.CheckConstraint(
                condition=models.Q(sequence__gte=1, sequence__lte=20),
                name="attendance_register_sequence",
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=["daily", "period"]), name="attendance_register_kind"
            ),
            models.CheckConstraint(
                condition=models.Q(state__in=["open", "submitted", "locked"]),
                name="attendance_register_state",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "institution", "date"]),
            models.Index(fields=["tenant", "unit", "date"]),
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.unit_id} {self.date}"


class Record(TenantScopedModel):
    institution = _fk("tenancy.Institution")
    register = _fk("attendance.Register", related_name="records")
    student = _fk("students.Student")
    date = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices)
    late_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    remark = models.CharField(max_length=160, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "attendance_record"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "register", "student"], name="attendance_record_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=_STATUS_VALUES), name="attendance_record_status"
            ),
            models.CheckConstraint(
                condition=models.Q(late_minutes__isnull=True)
                | (models.Q(status="late") & models.Q(late_minutes__lte=600)),
                name="attendance_record_late_minutes",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "student", "date"]),
            models.Index(fields=["tenant", "institution", "date"]),
        ]

    def __str__(self) -> str:
        return f"{self.student_id} {self.date} {self.status}"


class StaffRecord(TenantScopedModel):
    institution = _fk("tenancy.Institution")
    campus = _fk("tenancy.Campus", null=True)
    staff = _fk("staff.StaffProfile")
    date = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices)
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    remark = models.CharField(max_length=160, blank=True)
    marked_by = _fk("tenancy.Membership", null=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "attendance_staffrecord"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "staff", "date"], name="attendance_staffrecord_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=_STATUS_VALUES),
                name="attendance_staffrecord_status",
            ),
            models.CheckConstraint(
                condition=models.Q(check_in__isnull=True)
                | models.Q(check_out__isnull=True)
                | models.Q(check_out__gt=models.F("check_in")),
                name="attendance_staffrecord_times",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "institution", "date"])]

    def __str__(self) -> str:
        return f"{self.staff_id} {self.date} {self.status}"


class LeaveRequest(TenantScopedModel):
    class State(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    institution = _fk("tenancy.Institution")
    student = _fk("students.Student", null=True)
    staff = _fk("staff.StaffProfile", null=True)
    start_date = models.DateField()
    end_date = models.DateField()
    half_day = models.BooleanField(default=False)
    reason = models.CharField(max_length=500)
    state = models.CharField(max_length=16, choices=State.choices, default=State.PENDING)
    requested_by = _fk("tenancy.Membership", null=True)
    decided_by = _fk("tenancy.Membership", null=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    workflow_instance_id = models.UUIDField(null=True, blank=True)
    decision_note = models.CharField(max_length=300, blank=True)  # Phase 8 M3

    class Meta(TenantScopedModel.Meta):
        db_table = "attendance_leaverequest"
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(student__isnull=False) & models.Q(staff__isnull=True))
                | (models.Q(student__isnull=True) & models.Q(staff__isnull=False)),
                name="attendance_leave_one_person",
            ),
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="attendance_leave_dates",
            ),
            models.CheckConstraint(
                condition=~models.Q(half_day=True) | models.Q(end_date=models.F("start_date")),
                name="attendance_leave_half_day_single",
            ),
            models.CheckConstraint(
                condition=models.Q(state__in=["pending", "approved", "rejected", "cancelled"]),
                name="attendance_leave_state",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "student", "start_date"]),
            models.Index(fields=["tenant", "staff", "start_date"]),
            models.Index(fields=["tenant", "institution", "state"]),
        ]

    def __str__(self) -> str:
        return f"leave {self.start_date}..{self.end_date} {self.state}"


class AbsenceAlert(TenantScopedModel):
    """One absence alert per student and date (Phase 8 M5, ADR-078): the unique key makes the
    alert once a day even when several period registers mark the student absent."""

    institution = _fk("tenancy.Institution")
    student = _fk("students.Student")
    date = models.DateField()
    recipients = models.PositiveSmallIntegerField(default=0)

    class Meta(TenantScopedModel.Meta):
        db_table = "attendance_absencealert"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "student", "date"], name="attendance_alert_once_a_day"
            ),
        ]

    def __str__(self) -> str:
        return f"alert {self.student_id} {self.date}"


class StudentFlag(TenantScopedModel):
    """A student currently flagged for low attendance in a year (Phase 8 M5, P29): class
    teachers are told once when the flag appears; the row is removed when it clears."""

    institution = _fk("tenancy.Institution")
    student = _fk("students.Student")
    year = _fk("academics.AcademicYear")
    percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    by_rule = models.BooleanField(default=False)
    flagged_on = models.DateField()

    class Meta(TenantScopedModel.Meta):
        db_table = "attendance_studentflag"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "student", "year"], name="attendance_flag_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"flag {self.student_id} {self.year_id}"
