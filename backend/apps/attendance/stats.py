"""Attendance figures (Phase 8 M5; ADR-078, ADR-081 Q3).

A student's days in a date range come from the records of registers actually taken (no holiday
calendar): a day is *attended* when any record of that day is present or late, *absent* when a
record is absent and none attended, otherwise *not counted* (excused or leave). The percentage
is attended ÷ (attended + absent) days, ``None`` when nothing counts yet.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from apps.attendance.models import ATTENDED, Record, Status


@dataclass(frozen=True)
class Figures:
    attended_days: int
    absent_days: int
    late_days: int
    not_counted_days: int
    consecutive_absences: int

    @property
    def percent(self) -> Decimal | None:
        counted = self.attended_days + self.absent_days
        if not counted:
            return None
        value = Decimal(self.attended_days * 100) / Decimal(counted)
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def context(self) -> dict[str, Any]:
        """Variables of the ``attendance.flag`` and ``academics.promotion`` rules."""
        pct = self.percent
        return {
            "attendance.percent": float(pct) if pct is not None else None,
            "attendance.absent_days": self.absent_days,
            "attendance.late_days": self.late_days,
            "attendance.consecutive_absences": self.consecutive_absences,
        }


EMPTY = Figures(0, 0, 0, 0, 0)


def figures(student_ids: Any, start: dt.date, end: dt.date) -> dict[Any, Figures]:
    days: dict[Any, dict[dt.date, set[str]]] = {}
    rows = Record.objects.filter(
        student_id__in=student_ids, date__gte=start, date__lte=end
    ).values_list("student_id", "date", "status")
    for student, date, status in rows:
        days.setdefault(student, {}).setdefault(date, set()).add(status)
    out: dict[Any, Figures] = {}
    for student, by_date in days.items():
        attended = absent = late = other = streak = 0
        for date in sorted(by_date):
            statuses = by_date[date]
            if statuses & ATTENDED:
                attended += 1
                late += Status.LATE in statuses
                streak = 0
            elif Status.ABSENT in statuses:
                absent += 1
                streak += 1
            else:
                other += 1  # excused or leave: neither breaks nor extends a run of absences
        out[student] = Figures(attended, absent, late, other, streak)
    return out


def promotion_context(student: Any) -> dict[str, Any]:
    """``STUDENTS_PROMOTION_CONTEXT`` hook: attendance over the student's current year."""
    from apps.academics.models import AcademicYear
    from apps.students.selectors import current_year_id

    year_id = current_year_id(student.pk)
    year = AcademicYear.objects.filter(pk=year_id).first() if year_id else None
    if year is None:
        return EMPTY.context()
    return figures([student.pk], year.start_date, year.end_date).get(student.pk, EMPTY).context()
