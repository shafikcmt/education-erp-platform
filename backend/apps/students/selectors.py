"""Who sees which students: relationship scopes (Phase 7 M2; ADR-073).

Every list and detail of students goes through :func:`visible_students`, which unions four
grounds, each needing its own permission:

* **scope** — ``students.student.view`` in an organisational scope: the whole tenant, an
  institution, or a campus (students actively enrolled in a unit of that campus);
* **assigned** — ``students.student.view_assigned`` in the institution: students actively enrolled
  in a unit (or a unit below it) that the member teaches, through an offering of a year that is
  not closed. Other modules add their own assignment sources through ``STUDENTS_ASSIGNED_UNITS``
  (``staff`` adds class-teacher advisors in M3);
* **child** — ``students.child.view``: students linked to the guardian record whose login is the
  member;
* **own** — ``students.profile.view_own``: the student record whose login is the member.

Everything else is invisible, and views answer 404 for it (an unknown and a hidden student are
indistinguishable). Later modules (attendance, results) reuse these selectors.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db.models import Q, QuerySet
from django.utils.module_loading import import_string

from apps.core.tenancy import require_tenant
from apps.rbac.engine import ScopeTarget, has_perm
from apps.students.models import Enrollment, Guardian, Student

VIEW, ASSIGNED = "students.student.view", "students.student.view_assigned"
CHILD, OWN = "students.child.view", "students.profile.view_own"
GUARDIAN_VIEW = "students.guardian.view"
ALL_VIEW_CODES = (VIEW, ASSIGNED, CHILD, OWN)


def holds_in_institution(actor: Any, code: str, institution_id: Any) -> bool:
    """``code`` held for the institution itself or for one of its campuses (a teacher's or a
    class teacher's role is often campus-scoped)."""
    from apps.tenancy.models import Campus

    tenant_id = require_tenant().id
    if has_perm(actor, code, target=ScopeTarget(tenant_id, institution_id), use_cache=False):
        return True
    return any(
        has_perm(
            actor, code, target=ScopeTarget(tenant_id, institution_id, campus), use_cache=False
        )
        for campus in Campus.objects.filter(institution_id=institution_id).values_list(
            "pk", flat=True
        )
    )


def holds_anywhere(actor: Any, code: str) -> bool:
    """``code`` held in some scope of the tenant (guardian and student roles may be granted
    tenant-wide or in an institution, Phase 7 M8)."""
    from apps.tenancy.api.permissions import actor_targets

    return any(
        has_perm(actor, code, target=target, use_cache=False)
        for target in actor_targets(actor, require_tenant().id)
    )


def memberships(actor: Any) -> list[Any]:
    from apps.tenancy.models import Membership

    return list(
        Membership.objects.filter(user_id=actor.pk, status=Membership.Status.ACTIVE).values_list(
            "pk", flat=True
        )
    )


def _below(unit_ids: set[Any]) -> set[Any]:
    """The units and every unit below them (trees are shallow: a few levels at most)."""
    from apps.academics.models import Unit

    found, frontier = set(unit_ids), set(unit_ids)
    while frontier:
        frontier = (
            set(Unit.objects.filter(parent_id__in=frontier).values_list("pk", flat=True)) - found
        )
        found |= frontier
    return found


def taught_units(actor: Any, memberships: list[Any]) -> dict[Any, set[Any]]:
    """Units of the offerings the member teaches in years that are not closed, per institution."""
    from apps.academics.models import AcademicYear, Offering, OfferingTeacher

    offerings = Offering.objects.filter(
        pk__in=OfferingTeacher.objects.filter(membership_id__in=memberships).values("offering_id")
    ).exclude(year__status=AcademicYear.Status.CLOSED)
    units: dict[Any, set[Any]] = {}
    for institution_id, unit_id in offerings.values_list("institution_id", "unit_id"):
        units.setdefault(institution_id, set()).add(unit_id)
    return units


def assigned_units(actor: Any) -> set[Any]:
    """Units (and the units below them) whose students the member may see as assigned."""
    mine = memberships(actor)
    if not mine:
        return set()
    sources = getattr(settings, "STUDENTS_ASSIGNED_UNITS", ["apps.students.selectors.taught_units"])
    units: set[Any] = set()
    for path in sources:
        for institution_id, unit_ids in import_string(path)(actor, mine).items():
            if holds_in_institution(actor, ASSIGNED, institution_id):
                units |= unit_ids
    return _below(units) if units else set()


def _scope_filter(actor: Any) -> Q | None:
    """``students.student.view`` grounds; ``None`` means the whole tenant."""
    from apps.tenancy.api.permissions import actor_targets

    tenant = require_tenant()
    institutions, campuses = set(), set()
    for target in actor_targets(actor, tenant.id):
        if not has_perm(actor, VIEW, target=target, use_cache=False):
            continue
        if target.institution_id is None:
            return None  # tenant-wide
        if target.campus_id is None:
            institutions.add(target.institution_id)
        else:
            campuses.add(target.campus_id)
    query = Q(institution_id__in=institutions)
    if campuses:
        query |= Q(
            pk__in=Enrollment.objects.filter(
                status=Enrollment.Status.ACTIVE, unit__campus_id__in=campuses
            ).values("student_id")
        )
    return query


def visible_students(actor: Any) -> QuerySet[Student]:
    """Every student the member may see, by any of the four grounds."""
    if not getattr(actor, "is_authenticated", False):
        return Student.objects.none()
    scope = _scope_filter(actor)
    if scope is None:
        return Student.objects.all()
    query = scope
    units = assigned_units(actor)
    if units:
        query |= Q(
            pk__in=Enrollment.objects.filter(
                status=Enrollment.Status.ACTIVE, unit_id__in=units
            ).values("student_id")
        )
    mine = memberships(actor)
    if mine and holds_anywhere(actor, CHILD):
        query |= Q(guardian_links__guardian__membership_id__in=mine)
    if mine and holds_anywhere(actor, OWN):
        query |= Q(membership_id__in=mine)
    return Student.objects.filter(query).distinct()


def visible_student(actor: Any, student_id: Any) -> Student | None:
    """The student when visible to the member, else ``None`` (views answer 404)."""
    import uuid

    try:
        uuid.UUID(str(student_id))
    except ValueError:
        return None
    return visible_students(actor).filter(pk=student_id).first()


def guardians_shown(actor: Any, student: Student) -> list[Any]:
    """Guardian links of a visible student the member may see: all of them with
    ``students.guardian.view`` in the student's institution; otherwise a guardian sees only their
    own link (never another guardian's contact details, for example after a separation)."""
    from apps.students.models import StudentGuardian

    links = StudentGuardian.objects.filter(student=student).select_related("guardian")
    if holds_in_institution(actor, GUARDIAN_VIEW, student.institution_id):
        return list(links.order_by("-is_primary", "created_at"))
    mine = Guardian.objects.filter(membership_id__in=memberships(actor)).values("pk")
    return list(links.filter(guardian_id__in=mine))


def portal_units(actor: Any) -> set[Any]:
    """Units the member's children (``students.child.view``) or the member (``…view_own``) are
    actively enrolled in: what a guardian or a student sees in timetables (Phase 7 M7)."""
    mine = memberships(actor)
    if not mine:
        return set()
    query = Q(pk__in=[])
    if holds_anywhere(actor, CHILD):
        query |= Q(student__guardian_links__guardian__membership_id__in=mine)
    if holds_anywhere(actor, OWN):
        query |= Q(student__membership_id__in=mine)
    return set(
        Enrollment.objects.filter(query, status=Enrollment.Status.ACTIVE).values_list(
            "unit_id", flat=True
        )
    )


def unit_roster(unit_ids: set[Any], year_id: Any, on: Any) -> list[dict[str, Any]]:
    """Students enrolled in one of ``unit_ids`` for the year on the date ``on`` (an enrollment
    covers its start date up to its end date, if any): the roster of an attendance register
    (Phase 8 M2). Callers authorise; ordered by roll number, then name."""
    rows = (
        Enrollment.objects.filter(unit_id__in=unit_ids, year_id=year_id, start_date__lte=on)
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=on))
        .values("student_id", "student__name", "student__number", "roll_number")
        .order_by("roll_number", "student__name", "student_id")
    )
    seen: set[Any] = set()
    out = []
    for row in rows:
        if row["student_id"] in seen:  # moved within the year: the first row wins
            continue
        seen.add(row["student_id"])
        out.append(
            {
                "student_id": row["student_id"],
                "name": row["student__name"],
                "number": row["student__number"],
                "roll_number": row["roll_number"],
            }
        )
    return out


def units_below(unit_ids: set[Any]) -> set[Any]:
    """The units and every unit below them (shared with attendance, Phase 8 M2)."""
    return _below(set(unit_ids))


def relation_to(actor: Any, student_id: Any) -> set[str]:
    """``{"child"}`` when the member is a guardian of the student (with ``students.child.view``),
    ``{"own"}`` when it is the member's own record (with ``students.profile.view_own``); used by
    attendance leave requests (Phase 8 M3)."""
    mine = memberships(actor)
    out: set[str] = set()
    if not mine:
        return out
    if (
        holds_anywhere(actor, CHILD)
        and Student.objects.filter(
            pk=student_id, guardian_links__guardian__membership_id__in=mine
        ).exists()
    ):
        out.add("child")
    if (
        holds_anywhere(actor, OWN)
        and Student.objects.filter(pk=student_id, membership_id__in=mine).exists()
    ):
        out.add("own")
    return out


def current_units(student_ids: Any) -> dict[Any, tuple[Any, Any]]:
    """Each student's active enrollment unit and its campus (attendance, Phase 8 M3)."""
    rows = Enrollment.objects.filter(
        student_id__in=student_ids, status=Enrollment.Status.ACTIVE
    ).values_list("student_id", "unit_id", "unit__campus_id")
    return {student: (unit, campus) for student, unit, campus in rows}


def notice_memberships(student_ids: Any) -> dict[Any, list[Any]]:
    """Logins of each student's guardians who receive notices (attendance alerts, Phase 8 M5)."""
    from apps.students.models import StudentGuardian

    rows = StudentGuardian.objects.filter(
        student_id__in=student_ids, receives_notices=True, guardian__membership_id__isnull=False
    ).values_list("student_id", "guardian__membership_id")
    out: dict[Any, list[Any]] = {}
    for student, membership in rows:
        out.setdefault(student, []).append(membership)
    return out


def current_year_id(student_id: Any) -> Any:
    """The academic year of the student's active enrollment, if any (Phase 8 M5)."""
    return (
        Enrollment.objects.filter(student_id=student_id, status=Enrollment.Status.ACTIVE)
        .values_list("year_id", flat=True)
        .first()
    )


def active_enrollments(year_id: Any) -> dict[Any, Any]:
    """``{student: unit}`` of the year's active enrollments (attendance flags, Phase 8 M5)."""
    return dict(
        Enrollment.objects.filter(year_id=year_id, status=Enrollment.Status.ACTIVE).values_list(
            "student_id", "unit_id"
        )
    )


def active_units(institution_id: Any) -> set[Any]:
    """Units with active enrollments in the institution (attendance reports, Phase 8 M6)."""
    return set(
        Enrollment.objects.filter(
            institution_id=institution_id, status=Enrollment.Status.ACTIVE
        ).values_list("unit_id", flat=True)
    )


def active_enrollments_in(
    institution_id: Any, campuses: set[Any] | None, unit_id: Any = None
) -> list[dict[str, Any]]:
    """Active enrollments of the institution (optionally of some campuses or one unit), with
    the student's name and number (attendance reports, Phase 8 M6)."""
    rows = Enrollment.objects.filter(institution_id=institution_id, status=Enrollment.Status.ACTIVE)
    if campuses is not None:
        rows = rows.filter(unit__campus_id__in=campuses)
    if unit_id is not None:
        rows = rows.filter(unit_id=unit_id)
    return [
        {"student_id": r["student_id"], "name": r["student__name"], "number": r["student__number"],
         "unit": r["unit__name"], "roll_number": r["roll_number"]}
        for r in rows.order_by("unit__code", "roll_number", "student__name").values(
            "student_id", "student__name", "student__number", "unit__name", "roll_number"
        )[:5000]
    ]  # fmt: skip
