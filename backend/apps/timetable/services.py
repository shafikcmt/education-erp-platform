"""Timetable services (Phase 7 M7; ADR-071).

Writes need ``timetable.timetable.manage`` in the institution (checked uncached) and are
audited. Slots take their year, term and unit from the offering; the teacher must teach the
offering (Phase 6 offering teachers, ADR-063), and defaults to its primary teacher. Clashes are
refused in the same transaction:

* the database refuses a second slot for the same unit, teacher or room in the same year, term,
  weekday and period (unique constraints: concurrent writers can't double-book);
* the service also refuses what the constraints can't see: a period of another bell schedule
  whose times overlap, and a whole-year lesson against a term's lesson (or the reverse).
"""

from __future__ import annotations

import datetime as dt
import re
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpRequest

from apps.audit.services import record
from apps.core.tenancy import require_tenant
from apps.rbac.engine import ScopeTarget, require_perm
from apps.timetable.models import BellSchedule, Period, Room, Slot

if TYPE_CHECKING:
    from apps.identity.models import User

MANAGE = "timetable.timetable.manage"
_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")


def _authorise(actor: User, institution_id: Any) -> None:
    require_perm(
        actor, MANAGE, target=ScopeTarget(require_tenant().id, institution_id), use_cache=False
    )


def _audit(action: str, actor: Any, request: HttpRequest | None, obj: Any, **meta: Any) -> None:
    record(action, actor=actor, request=request,
           target_type=f"timetable.{type(obj).__name__.lower()}", target_id=obj.pk,
           metadata=meta)  # fmt: skip


def _institution(institution: Any) -> Any:
    from apps.tenancy.models import Institution

    row = Institution.objects.filter(pk=getattr(institution, "pk", institution)).first()
    if row is None:
        raise ValidationError({"institution": "Unknown institution."})
    return row


def _code(code: Any) -> str:
    text = str(code or "").strip()
    if not _CODE.match(text):
        raise ValidationError(
            {"code": "Use 1-32 letters, digits and . - _ (starting alphanumeric)."}
        )
    return text


def _name(name: Any, limit: int = 120) -> str:
    text = str(name or "").strip()
    if not text or len(text) > limit:
        raise ValidationError({"name": f"Give a name of at most {limit} characters."})
    return text


# --------------------------------------------------------------------------- schedules, rooms
@transaction.atomic
def create_schedule(
    *, actor: User, institution: Any, code: str, name: str, request: HttpRequest | None = None
) -> BellSchedule:
    inst = _institution(institution)
    _authorise(actor, inst.pk)
    code = _code(code)
    if BellSchedule.objects.filter(institution=inst, code=code).exists():
        raise ValidationError({"code": "This code is already used."})
    row = BellSchedule.objects.create(
        institution=inst, code=code, name=_name(name), created_by=actor.pk
    )
    _audit("timetable.schedule.created", actor, request, row, ref=code)
    return row


@transaction.atomic
def add_period(
    *,
    actor: User,
    schedule: BellSchedule,
    order: int,
    name: str,
    start_time: dt.time,
    end_time: dt.time,
    is_break: bool = False,
    request: HttpRequest | None = None,
) -> Period:
    schedule = BellSchedule.objects.select_for_update().get(pk=schedule.pk)
    _authorise(actor, schedule.institution_id)
    if not 1 <= int(order) <= 30:
        raise ValidationError({"order": "Periods are numbered 1-30."})
    if end_time <= start_time:
        raise ValidationError({"end_time": "The period ends after it starts."})
    if Period.objects.filter(schedule=schedule, order=order).exists():
        raise ValidationError({"order": "This schedule already has a period with that number."})
    overlapping = Period.objects.filter(
        schedule=schedule, start_time__lt=end_time, end_time__gt=start_time
    )
    if overlapping.exists():
        raise ValidationError({"start_time": "Periods of one schedule don't overlap."})
    row = Period.objects.create(
        institution_id=schedule.institution_id, schedule=schedule, order=order,
        name=_name(name, 60), start_time=start_time, end_time=end_time, is_break=is_break,
        created_by=actor.pk,
    )  # fmt: skip
    _audit("timetable.period.created", actor, request, row)
    return row


@transaction.atomic
def create_room(
    *,
    actor: User,
    institution: Any,
    code: str,
    name: str,
    campus: Any = None,
    capacity: int | None = None,
    request: HttpRequest | None = None,
) -> Room:
    from apps.tenancy.models import Campus

    inst = _institution(institution)
    _authorise(actor, inst.pk)
    code = _code(code)
    if Room.objects.filter(institution=inst, code=code).exists():
        raise ValidationError({"code": "This code is already used."})
    campus_row = None
    if campus not in (None, ""):
        campus_row = Campus.objects.filter(
            pk=getattr(campus, "pk", campus), institution=inst
        ).first()
        if campus_row is None:
            raise ValidationError({"campus": "Choose a campus of this institution."})
    if capacity is not None and not 0 < int(capacity) <= 10_000:
        raise ValidationError({"capacity": "Give a capacity between 1 and 10000."})
    row = Room.objects.create(
        institution=inst, campus=campus_row, code=code, name=_name(name), capacity=capacity,
        created_by=actor.pk,
    )  # fmt: skip
    _audit("timetable.room.created", actor, request, row, ref=code)
    return row


# --------------------------------------------------------------------------- slots
def _same_time(period: Period) -> Q:
    """Periods (of any schedule of the institution) overlapping ``period``'s times."""
    return Q(period__start_time__lt=period.end_time, period__end_time__gt=period.start_time)


def _clash(slot: dict[str, Any], period: Period) -> str:
    """What the new slot would clash with, beyond the unique constraints, or ``""``."""
    others = Slot.objects.filter(year_id=slot["year_id"], weekday=slot["weekday"]).filter(
        _same_time(period)
    )
    if slot["term_id"] is not None:  # a term's lesson meets that term's and the whole-year ones
        others = others.filter(Q(term_id=slot["term_id"]) | Q(term__isnull=True))
    checks = {"unit": Q(unit_id=slot["unit_id"])}
    if slot["teacher_id"] is not None:
        checks["teacher"] = Q(teacher_id=slot["teacher_id"])
    if slot["room_id"] is not None:
        checks["room"] = Q(room_id=slot["room_id"])
    for field, condition in checks.items():
        if others.filter(condition).exists():
            return field
    return ""


_CLASH_MESSAGES = {
    "unit": "This unit already has a lesson at that time.",
    "teacher": "The teacher already teaches at that time.",
    "room": "The room is already in use at that time.",
}
_CONSTRAINTS = {
    "timetable_slot_unit_clash": "unit",
    "timetable_slot_teacher_clash": "teacher",
    "timetable_slot_room_clash": "room",
}


@transaction.atomic
def create_slot(
    *,
    actor: User,
    offering: Any,
    weekday: int,
    period: Any,
    teacher: Any = "default",
    room: Any = None,
    request: HttpRequest | None = None,
) -> Slot:
    """A weekly lesson of ``offering``. ``teacher`` is a membership teaching the offering, the
    primary teacher by default, or ``None`` for none yet."""
    from apps.academics.models import AcademicYear, Offering, OfferingTeacher

    offer = Offering.objects.filter(pk=getattr(offering, "pk", offering)).first()
    if offer is None:
        raise ValidationError({"offering": "Unknown offering."})
    inst = offer.institution_id
    _authorise(actor, inst)
    year = AcademicYear.objects.get(pk=offer.year_id)
    if year.status == AcademicYear.Status.CLOSED:
        raise ValidationError({"offering": "The offering's academic year is closed."})
    if int(weekday) not in Slot.Weekday.values:
        raise ValidationError({"weekday": "Choose a weekday (1 = Monday … 7 = Sunday)."})
    period_row = Period.objects.filter(
        pk=getattr(period, "pk", period), institution_id=inst
    ).first()
    if period_row is None:
        raise ValidationError({"period": "Choose a period of this institution."})
    if period_row.is_break:
        raise ValidationError({"period": "Breaks take no lessons."})
    teachers = OfferingTeacher.objects.filter(offering=offer)
    if teacher == "default":
        teacher_id = (
            teachers.filter(role=OfferingTeacher.Role.PRIMARY)
            .order_by("created_at")
            .values_list("membership_id", flat=True)
            .first()
        )
    elif teacher in (None, ""):
        teacher_id = None
    else:
        teacher_id = (
            teachers.filter(membership_id=getattr(teacher, "pk", teacher))
            .values_list("membership_id", flat=True)
            .first()
        )
        if teacher_id is None:
            raise ValidationError({"teacher": "Choose a teacher of this offering."})
    room_row = None
    if room not in (None, ""):
        room_row = Room.objects.filter(
            pk=getattr(room, "pk", room), institution_id=inst, archived_at__isnull=True
        ).first()
        if room_row is None:
            raise ValidationError({"room": "Choose a room of this institution."})
    values = {
        "institution_id": inst, "year_id": offer.year_id, "term_id": offer.term_id,
        "unit_id": offer.unit_id, "weekday": int(weekday), "period": period_row,
        "offering": offer, "teacher_id": teacher_id, "room": room_row,
    }  # fmt: skip
    clash = _clash({**values, "room_id": room_row.pk if room_row else None}, period_row)
    if clash:
        raise ValidationError({clash: _CLASH_MESSAGES[clash]})
    try:
        with transaction.atomic():
            row = Slot.objects.create(created_by=actor.pk, **values)
    except IntegrityError as exc:  # a concurrent writer took the same unit, teacher or room
        field = next((f for c, f in _CONSTRAINTS.items() if c in str(exc)), "unit")
        raise ValidationError({field: _CLASH_MESSAGES[field]}) from None
    _audit("timetable.slot.created", actor, request, row, weekday=row.weekday)
    return row


@transaction.atomic
def delete_slot(*, actor: User, slot: Slot, request: HttpRequest | None = None) -> None:
    row = Slot.objects.select_for_update().get(pk=slot.pk)
    _authorise(actor, row.institution_id)
    pk = row.pk
    row.delete()
    record("timetable.slot.deleted", actor=actor, request=request, target_type="timetable.slot",
           target_id=pk, metadata={})  # fmt: skip
