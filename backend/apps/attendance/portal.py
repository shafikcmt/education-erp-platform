"""What guardians and students see of attendance (Phase 8 M6; plan §8).

Only one's children (``students.child.view``) or oneself (``students.profile.view_own``):
a month's days (one status per day), the year-to-date figures, any current flag and the
leave requests. Anything else is ``None`` (the view answers 404).
"""

from __future__ import annotations

from typing import Any

from apps.attendance.models import LeaveRequest, Record, StudentFlag
from apps.attendance.reports import _day_status, _month
from apps.attendance.stats import EMPTY, figures


def month(actor: Any, student_id: Any, value: str) -> dict[str, Any] | None:
    from apps.academics.models import AcademicYear
    from apps.students.selectors import current_year_id, relation_to

    if not relation_to(actor, student_id):
        return None
    start, end = _month(value)
    days: dict[str, set[str]] = {}
    for date, status in Record.objects.filter(
        student_id=student_id, date__gte=start, date__lte=end
    ).values_list("date", "status"):
        days.setdefault(date.isoformat(), set()).add(status)
    year = AcademicYear.objects.filter(pk=current_year_id(student_id)).first()
    stats = figures([student_id], year.start_date, year.end_date) if year else {}
    f = stats.get(student_id, EMPTY)
    leave = LeaveRequest.objects.filter(student_id=student_id).order_by("-start_date")[:20]
    return {
        "student": student_id,
        "month": start.strftime("%Y-%m"),
        "days": {d: _day_status(s) for d, s in sorted(days.items())},
        "percent": f.percent,
        "absent_days": f.absent_days,
        "late_days": f.late_days,
        "flagged": StudentFlag.objects.filter(student_id=student_id).exists(),
        "leave": list(leave),
    }
