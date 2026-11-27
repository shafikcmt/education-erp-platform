"""What the portal shows (Phase 7 M8; ADR-069, ADR-073).

Only the **child** and **own** grounds of ``students``: a guardian's children (their guardian
record's login is the member, ``students.child.view``) and the student's own record
(``students.profile.view_own``). Staff scope never applies here, so a teacher who is also a
parent sees only their own children in the portal.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Q, QuerySet

from apps.students.models import Student, StudentGuardian
from apps.students.selectors import CHILD, OWN, holds_anywhere, memberships


def children(actor: Any) -> QuerySet[Student]:
    mine = memberships(actor)
    if not mine:
        return Student.objects.none()
    query = Q(pk__in=[])
    if holds_anywhere(actor, CHILD):
        query |= Q(guardian_links__guardian__membership_id__in=mine)
    if holds_anywhere(actor, OWN):
        query |= Q(membership_id__in=mine)
    return Student.objects.filter(query).distinct().order_by("name")


def child(actor: Any, student_id: Any) -> Student | None:
    import uuid

    try:
        uuid.UUID(str(student_id))
    except ValueError:
        return None
    return children(actor).filter(pk=student_id).first()


def relation(actor: Any, student: Student) -> str:
    """``self`` or the guardian's relation to the child (``mother``, ``father`` …)."""
    mine = memberships(actor)
    if student.membership_id in mine:
        return "self"
    link = StudentGuardian.objects.filter(
        student=student, guardian__membership_id__in=mine
    ).values_list("relation", flat=True)
    return link.first() or "guardian"


def current_enrollment(student: Student) -> dict[str, Any] | None:
    from apps.students.models import Enrollment

    row = (
        Enrollment.objects.filter(student=student, status=Enrollment.Status.ACTIVE)
        .order_by("-start_date")
        .values("unit_id", "unit__name", "year_id", "year__name", "roll_number")
        .first()
    )
    if row is None:
        return None
    return {
        "unit": row["unit_id"], "unit_name": row["unit__name"], "year": row["year_id"],
        "year_name": row["year__name"], "roll_number": row["roll_number"],
    }  # fmt: skip


def timetable(unit_id: Any) -> list[dict[str, Any]]:
    """The unit's weekly lessons when the tenant has ``timetable`` (else none)."""
    from apps.module_registry.entitlements import is_entitled

    if unit_id is None or not is_entitled("timetable"):
        return []
    from apps.timetable.selectors import slots

    rows = slots().filter(unit_id=unit_id).values(
        "weekday", "period__start_time", "period__end_time", "period__name",
        "offering__subject__name", "room__code",
    )  # fmt: skip
    return [
        {
            "weekday": r["weekday"],
            "start_time": r["period__start_time"],
            "end_time": r["period__end_time"],
            "period_name": r["period__name"],
            "subject_name": r["offering__subject__name"],
            "room_code": r["room__code"] or "",
        }
        for r in rows
    ]
