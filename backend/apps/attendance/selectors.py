"""Who may mark and see which attendance registers (Phase 8 M2; ADR-077, ADR-073).

* **Mark (assigned)** — ``attendance.record.mark`` in the register's institution (or one of its
  campuses), and the member either advises the register's unit (or a unit above it) for a
  daily register, or teaches the register's offering for a period register.
* **Manage** — ``attendance.record.manage`` in the register's institution or its campus: any
  register there, edits past the edit window, unlocking.
* **View** — ``attendance.record.view`` in the institution or the register's campus, or any of
  the above.

Everything else is invisible: views answer 404 for it. Checks are uncached (``use_cache=False``).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from django.db.models import Q, QuerySet

from apps.attendance.config import config_for
from apps.attendance.models import LeaveRequest, Record, Register
from apps.core.tenancy import require_tenant
from apps.rbac.engine import ScopeTarget, has_perm

MARK = "attendance.record.mark"
VIEW = "attendance.record.view"
MANAGE = "attendance.record.manage"


def _target(institution_id: Any, campus_id: Any = None) -> ScopeTarget:
    return ScopeTarget(require_tenant().id, institution_id, campus_id)


def holds_at(actor: Any, code: str, institution_id: Any, campus_id: Any = None) -> bool:
    """``code`` at the institution, or at the campus when the register has one (an
    institution-wide grant covers its campuses)."""
    return has_perm(actor, code, target=_target(institution_id, campus_id), use_cache=False)


def _memberships(actor: Any) -> list[Any]:
    from apps.students.selectors import memberships

    return memberships(actor)


def advised_units(actor: Any, institution_id: Any) -> set[Any]:
    """Units (and the units below them) the member advises in the institution."""
    from apps.staff.selectors import advised_units as advised
    from apps.students.selectors import units_below

    units = advised(actor, _memberships(actor)).get(institution_id, set())
    return units_below(units) if units else set()


def taught_offerings(actor: Any, institution_id: Any | None = None) -> QuerySet[Any]:
    from apps.academics.models import AcademicYear, Offering, OfferingTeacher

    rows = Offering.objects.filter(
        pk__in=OfferingTeacher.objects.filter(membership_id__in=_memberships(actor)).values(
            "offering_id"
        )
    ).exclude(year__status=AcademicYear.Status.CLOSED)
    return rows.filter(institution_id=institution_id) if institution_id else rows


def _holds_mark(actor: Any, institution_id: Any) -> bool:
    from apps.students.selectors import holds_in_institution

    return holds_in_institution(actor, MARK, institution_id)


def assigned(actor: Any, *, institution_id: Any, kind: str, unit_id: Any, offering_id: Any) -> bool:
    """The member may mark this register as its class teacher or subject teacher."""
    if not _holds_mark(actor, institution_id):
        return False
    if kind == Register.Kind.DAILY:
        return unit_id in advised_units(actor, institution_id)
    return taught_offerings(actor, institution_id).filter(pk=offering_id).exists()


def can_mark(actor: Any, register: Register) -> bool:
    return holds_at(actor, MANAGE, register.institution_id, register.campus_id) or assigned(
        actor,
        institution_id=register.institution_id,
        kind=register.kind,
        unit_id=register.unit_id,
        offering_id=register.offering_id,
    )


def can_view(actor: Any, register: Register) -> bool:
    return holds_at(actor, VIEW, register.institution_id, register.campus_id) or can_mark(
        actor, register
    )


def visible_register(actor: Any, register_id: Any) -> Register | None:
    row = Register.objects.filter(pk=register_id).first()
    return row if row is not None and can_view(actor, row) else None


def registers_in(actor: Any, institution_id: Any) -> QuerySet[Register]:
    """Registers of the institution the member may see: all of them with view or manage at the
    institution, a campus's with the code at that campus, plus the registers they may mark."""
    from apps.tenancy.models import Campus

    rows = Register.objects.filter(institution_id=institution_id)
    if holds_at(actor, VIEW, institution_id) or holds_at(actor, MANAGE, institution_id):
        return rows
    campuses = [
        c
        for c in Campus.objects.filter(institution_id=institution_id).values_list("pk", flat=True)
        if holds_at(actor, VIEW, institution_id, c) or holds_at(actor, MANAGE, institution_id, c)
    ]
    grounds = Q(campus_id__in=campuses)
    if _holds_mark(actor, institution_id):
        units = advised_units(actor, institution_id)
        offerings = taught_offerings(actor, institution_id).values("pk")
        grounds |= Q(kind=Register.Kind.DAILY, unit_id__in=units)
        grounds |= Q(kind=Register.Kind.PERIOD, offering_id__in=offerings)
    return rows.filter(grounds)


# --------------------------------------------------------------------------- the roster
def roster(register: Register) -> list[dict[str, Any]]:
    """The register's students with their saved status, or the approved leave of the day, or
    the configured default (``status_source`` says which)."""
    from apps.students.selectors import unit_roster, units_below

    units = {register.unit_id}
    if register.kind == Register.Kind.PERIOD:
        units = units_below(units)  # e.g. a programme-level course with students in batches
    people = unit_roster(units, register.year_id, register.date)
    saved = {
        r.student_id: r
        for r in Record.objects.filter(register=register).only(
            "student_id", "status", "late_minutes", "remark"
        )
    }
    on_leave = set(
        LeaveRequest.objects.filter(
            student_id__in=[p["student_id"] for p in people],
            state=LeaveRequest.State.APPROVED,
            start_date__lte=register.date,
            end_date__gte=register.date,
        ).values_list("student_id", flat=True)
    )
    default = config_for(register.institution_id, register.campus_id).default_status
    for person in people:
        record = saved.get(person["student_id"])
        if record is not None:
            person.update(
                status=record.status, late_minutes=record.late_minutes, remark=record.remark,
                status_source="saved", on_leave=person["student_id"] in on_leave,
            )  # fmt: skip
        else:
            leave = person["student_id"] in on_leave
            person.update(
                status="leave" if leave else default, late_minutes=None, remark="",
                status_source="leave" if leave else "default", on_leave=leave,
            )  # fmt: skip
    return people


# --------------------------------------------------------------------------- the work list
@dataclass(frozen=True)
class Due:
    """A register the member is expected to take on a date (existing or not yet opened)."""

    kind: str
    institution_id: Any
    unit_id: Any
    unit_name: str
    offering_id: Any
    subject_name: str
    register: Register | None


def due_for(actor: Any, on: dt.date) -> list[Due]:
    """Today's registers of a class or subject teacher: daily registers of the leaf units they
    advise (where the mode takes daily registers) and period registers of the offerings they
    teach (where it takes period registers), each with the register if already opened."""
    from apps.academics.models import AcademicYear, Unit

    out: list[Due] = []
    institutions: set[Any] = set()
    from apps.staff.selectors import advised_units as advised

    advised_by_inst = advised(actor, _memberships(actor))
    institutions |= set(advised_by_inst)
    offerings = list(
        taught_offerings(actor)
        .filter(year__start_date__lte=on, year__end_date__gte=on)
        .select_related("unit", "subject")
    )
    institutions |= {o.institution_id for o in offerings}
    markable = {i for i in institutions if _holds_mark(actor, i)}
    open_years = AcademicYear.objects.exclude(status=AcademicYear.Status.CLOSED).filter(
        start_date__lte=on, end_date__gte=on
    )
    for inst in sorted(markable, key=str):
        if not open_years.filter(institution_id=inst).exists():
            continue
        leaves = Unit.objects.filter(pk__in=advised_units(actor, inst), archived_at__isnull=True)
        leaves = leaves.exclude(pk__in=Unit.objects.filter(parent__isnull=False).values("parent"))
        for unit in leaves.order_by("code"):
            if not config_for(inst, unit.campus_id).takes_daily:
                continue
            reg = Register.objects.filter(
                kind=Register.Kind.DAILY, unit=unit, date=on
            ).first()  # fmt: skip
            out.append(Due("daily", inst, unit.pk, unit.name, None, "", reg))
    for offering in offerings:
        if offering.institution_id not in markable:
            continue
        if not config_for(offering.institution_id, offering.unit.campus_id).takes_period:
            continue
        reg = (
            Register.objects.filter(kind=Register.Kind.PERIOD, offering=offering, date=on)
            .order_by("sequence")
            .first()
        )
        out.append(
            Due("period", offering.institution_id, offering.unit_id, offering.unit.name,
                offering.pk, offering.subject.name, reg)
        )  # fmt: skip
    return out
