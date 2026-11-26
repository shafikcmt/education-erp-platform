"""Bell schedules, periods, rooms and timetable slots (Phase 7 M7; ADR-071).

* ``BellSchedule`` / ``Period``: per institution; ordered periods with start and end times;
  breaks are periods that take no slots.
* ``Room``: per institution, optionally on a campus, with a capacity.
* ``Slot``: one weekly lesson: an academic year (and the offering's term), a unit, a weekday, a
  period, the offering, its teacher (a membership, ADR-063) and a room.

Clashes are refused by unique constraints (one unit, one teacher, one room per year, term,
weekday and period), so concurrent writers cannot double-book; the service also refuses
overlaps the constraints can't see (another bell schedule's overlapping period, a whole-year
lesson against a term's). Every table is tenant-owned with standard RLS (``timetable.0002``).
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
        db_constraint=False,  # enforced by composite tenant keys (timetable.0002)
    )


class BellSchedule(TenantScopedModel):
    institution = _fk("tenancy.Institution")
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "timetable_bellschedule"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "institution", "code"], name="timetable_schedule_code_unique"
            ),
            models.UniqueConstraint(
                fields=["tenant", "institution", "id"], name="timetable_schedule_tenant_key"
            ),
        ]

    def __str__(self) -> str:
        return self.code


class Period(TenantScopedModel):
    institution = _fk("tenancy.Institution")
    schedule = _fk("timetable.BellSchedule", related_name="periods")
    order = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=60)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_break = models.BooleanField(default=False)

    class Meta(TenantScopedModel.Meta):
        db_table = "timetable_period"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "schedule", "order"], name="timetable_period_order_unique"
            ),
            models.UniqueConstraint(
                fields=["tenant", "institution", "id"], name="timetable_period_tenant_key"
            ),
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="timetable_period_times",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Room(TenantScopedModel):
    institution = _fk("tenancy.Institution")
    campus = _fk("tenancy.Campus", null=True)
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "timetable_room"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "institution", "code"], name="timetable_room_code_unique"
            ),
            models.UniqueConstraint(
                fields=["tenant", "institution", "id"], name="timetable_room_tenant_key"
            ),
        ]

    def __str__(self) -> str:
        return self.code


class Slot(TenantScopedModel):
    class Weekday(models.IntegerChoices):
        MONDAY = 1, "Monday"
        TUESDAY = 2, "Tuesday"
        WEDNESDAY = 3, "Wednesday"
        THURSDAY = 4, "Thursday"
        FRIDAY = 5, "Friday"
        SATURDAY = 6, "Saturday"
        SUNDAY = 7, "Sunday"

    institution = _fk("tenancy.Institution")
    year = _fk("academics.AcademicYear")
    term = _fk("academics.Term", null=True)
    unit = _fk("academics.Unit")
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    period = _fk("timetable.Period")
    offering = _fk("academics.Offering")
    teacher = _fk("tenancy.Membership", null=True)
    room = _fk("timetable.Room", null=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "timetable_slot"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "year", "term", "unit", "weekday", "period"],
                nulls_distinct=False,
                name="timetable_slot_unit_clash",
            ),
            models.UniqueConstraint(
                fields=["tenant", "year", "term", "teacher", "weekday", "period"],
                condition=models.Q(teacher__isnull=False),
                nulls_distinct=False,
                name="timetable_slot_teacher_clash",
            ),
            models.UniqueConstraint(
                fields=["tenant", "year", "term", "room", "weekday", "period"],
                condition=models.Q(room__isnull=False),
                nulls_distinct=False,
                name="timetable_slot_room_clash",
            ),
            models.CheckConstraint(
                condition=models.Q(weekday__gte=1, weekday__lte=7), name="timetable_slot_weekday"
            ),
        ]
        indexes = [models.Index(fields=["tenant", "year", "unit"])]

    def __str__(self) -> str:
        return f"{self.unit_id} {self.weekday}/{self.period_id}"
