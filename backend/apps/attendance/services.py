"""Marking attendance (Phase 8 M2; ADR-077).

* **Open** a register: the unit's daily register or an offering's period register on a date,
  if the institution's mode takes that kind (Studio setting), the date is not in the future and
  lies in an open academic year. Opening twice returns the same register (concurrent openers
  meet the partial unique constraint and read the winner's row).
* **Save** the statuses of the register's students in one request, with the register's
  ``version``: a stale version is refused (:class:`StaleRegister`, 409) and nothing changes;
  otherwise the version increases. Students outside the roster are refused. Within
  ``edit_window_days`` of the date the marker may edit; later edits need
  ``attendance.record.manage`` and a reason (step-up at the API). Locked registers are refused.
* **Submit** once every student of the roster has a status; ``ATTENDANCE_SUBMITTED_HANDLERS``
  run after commit (absence alerts, M5).
* **Unlock** with ``attendance.record.manage`` and a reason. The nightly job (P29, M5) locks
  registers older than ``lock_after_days`` again.

Every write is audited with ids and statuses; free-text reasons and remarks stay out of the
audit log (only that a reason was given).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone
from django.utils.module_loading import import_string
from rest_framework import status as http

from apps.attendance import selectors
from apps.attendance.config import config_for
from apps.attendance.models import Record, Register, Status
from apps.audit.services import record as audit
from apps.core.exceptions import ProblemError
from apps.core.tenancy import require_tenant

if TYPE_CHECKING:
    from apps.identity.models import User

MAX_REASON = 300


class StaleRegister(ProblemError):  # noqa: N818 - a Problem Details response, like identity.errors
    status_code = http.HTTP_409_CONFLICT
    problem_code = "stale_register"
    title = "The register changed"
    default_detail = "Someone saved this register after you opened it. Reload and try again."


def today() -> dt.date:
    return timezone.localdate()


def _audit(
    action: str, actor: Any, request: HttpRequest | None, row: Register, **meta: Any
) -> None:
    audit(action, actor=actor, request=request, target_type="attendance.register",
          target_id=row.pk, metadata=meta)  # fmt: skip


def _membership_id(actor: Any) -> Any:
    from apps.tenancy.models import Membership

    return (
        Membership.objects.filter(user_id=actor.pk, status=Membership.Status.ACTIVE)
        .values_list("pk", flat=True)
        .first()
    )


def _reason(reason: Any, *, required: bool) -> str:
    text = str(reason or "").strip()
    if required and not text:
        raise ValidationError({"reason": "Give a reason for this change."})
    if len(text) > MAX_REASON:
        raise ValidationError({"reason": f"At most {MAX_REASON} characters."})
    return text


def _not_future(on: dt.date) -> None:
    if on > today():
        raise ValidationError({"date": "Attendance can't be taken for a future date."})


def _year_for(institution_id: Any, on: dt.date) -> Any:
    from apps.academics.models import AcademicYear

    year = (
        AcademicYear.objects.filter(
            institution_id=institution_id, start_date__lte=on, end_date__gte=on
        )
        .exclude(status=AcademicYear.Status.CLOSED)
        .first()
    )
    if year is None:
        raise ValidationError({"date": "The date is not in an open academic year."})
    return year


def _leaf_unit(unit: Any) -> Any:
    from apps.academics.models import Unit

    row = Unit.objects.filter(pk=getattr(unit, "pk", unit), archived_at__isnull=True).first()
    if row is None:
        raise ValidationError({"unit": "Unknown unit."})
    if Unit.objects.filter(parent=row).exists():
        raise ValidationError({"unit": "Daily registers are taken for units students sit in."})
    return row


def _offering(offering: Any) -> Any:
    from apps.academics.models import AcademicYear, Offering

    row = (
        Offering.objects.filter(pk=getattr(offering, "pk", offering))
        .exclude(year__status=AcademicYear.Status.CLOSED)
        .select_related("unit", "year")
        .first()
    )
    if row is None:
        raise ValidationError({"offering": "Unknown offering."})
    return row


# --------------------------------------------------------------------------- open
def open_register(
    *,
    actor: User,
    kind: str,
    on: dt.date,
    unit: Any = None,
    offering: Any = None,
    sequence: int = 1,
    request: HttpRequest | None = None,
) -> Register:
    _not_future(on)
    if kind == Register.Kind.DAILY:
        unit_row = _leaf_unit(unit)
        year, term, offering_row = _year_for(unit_row.institution_id, on), None, None
    elif kind == Register.Kind.PERIOD:
        offering_row = _offering(offering)
        unit_row, year, term = offering_row.unit, offering_row.year, offering_row.term_id
        if not (year.start_date <= on <= year.end_date):
            raise ValidationError({"date": "The date is outside the offering's academic year."})
    else:
        raise ValidationError({"kind": "Choose daily or period."})
    if not 1 <= int(sequence) <= 20:
        raise ValidationError({"sequence": "Between 1 and 20."})
    inst = unit_row.institution_id
    config = config_for(inst, unit_row.campus_id)
    if kind == Register.Kind.DAILY and not config.takes_daily:
        raise ValidationError({"kind": "This institution takes period registers only."})
    if kind == Register.Kind.PERIOD and not config.takes_period:
        raise ValidationError({"kind": "This institution takes daily registers only."})
    probe = Register(
        institution_id=inst, campus_id=unit_row.campus_id, unit=unit_row, kind=kind,
        offering=offering_row,
    )  # fmt: skip
    if not selectors.can_mark(actor, probe):
        raise PermissionDenied("You can't take this register.")
    lookup: dict[str, Any] = {"kind": kind, "date": on}
    if kind == Register.Kind.DAILY:
        lookup["unit"] = unit_row
    else:
        lookup.update(offering=offering_row, sequence=int(sequence))
    existing = Register.objects.filter(**lookup).first()
    if existing is not None:
        return existing
    try:
        with transaction.atomic():
            row = Register.objects.create(
                **{**lookup, "unit": unit_row}, institution_id=inst,
                campus_id=unit_row.campus_id, year=year, term_id=term,
                taken_by_id=_membership_id(actor), created_by=actor.pk,
            )  # fmt: skip
    except IntegrityError:
        winner = Register.objects.filter(**lookup).first()
        if winner is None:
            raise
        return winner
    _audit("attendance.register.opened", actor, request, row, kind=kind, date=on.isoformat())
    return row


# --------------------------------------------------------------------------- save, submit
def _locked_for_update(register: Register) -> Register:
    return Register.objects.select_for_update().get(pk=register.pk)


def outside_window(register: Register) -> bool:
    window = config_for(register.institution_id, register.campus_id).edit_window_days
    return register.date < today() - dt.timedelta(days=window)


def _clean_entries(entries: Any, roster_ids: set[Any]) -> dict[Any, dict[str, Any]]:
    import uuid

    if not isinstance(entries, list) or not entries:
        raise ValidationError({"entries": "Give at least one student's status."})
    if len(entries) > 2000:
        raise ValidationError({"entries": "Too many entries."})
    clean: dict[Any, dict[str, Any]] = {}
    for item in entries:
        try:
            student = uuid.UUID(str(item.get("student")))
        except (AttributeError, ValueError):
            raise ValidationError({"entries": "Each entry names a student."}) from None
        if student not in roster_ids:
            raise ValidationError({"entries": "A student is not on this register."})
        if student in clean:
            raise ValidationError({"entries": "A student appears twice."})
        value = item.get("status")
        if value not in Status.values:
            raise ValidationError({"entries": "Unknown status."})
        minutes = item.get("late_minutes")
        if minutes is not None and (
            value != Status.LATE or not isinstance(minutes, int) or not 0 <= minutes <= 600
        ):
            raise ValidationError({"entries": "Late minutes go with the late status (0-600)."})
        remark = str(item.get("remark") or "").strip()
        if len(remark) > 160:
            raise ValidationError({"entries": "Remarks are at most 160 characters."})
        clean[student] = {"status": value, "late_minutes": minutes, "remark": remark}
    return clean


@transaction.atomic
def save(
    *,
    actor: User,
    register: Register,
    version: int,
    entries: Any,
    reason: str = "",
    request: HttpRequest | None = None,
) -> Register:
    row = _locked_for_update(register)
    if not selectors.can_mark(actor, row):
        raise PermissionDenied("You can't take this register.")
    if row.version != version:
        raise StaleRegister(extra={"version": row.version})
    if row.state == Register.State.LOCKED:
        raise ValidationError({"register": "This register is locked. Unlock it first."})
    _not_future(row.date)
    late_edit = outside_window(row)
    if late_edit and not selectors.holds_at(actor, selectors.MANAGE, row.institution_id,
                                            row.campus_id):  # fmt: skip
        raise PermissionDenied("Only attendance managers can change older registers.")
    text = _reason(reason, required=late_edit)
    roster_ids = {p["student_id"] for p in selectors.roster(row)}
    clean = _clean_entries(entries, roster_ids)
    before = {r.student_id: r for r in Record.objects.filter(register=row)}
    changes: list[str] = []  # "<student>:<old>><new>" (ids and statuses only)
    created: list[Record] = []
    for student, values in clean.items():
        old = before.get(student)
        if old is None:
            created.append(
                Record(institution_id=row.institution_id, register=row, student_id=student,
                       date=row.date, created_by=actor.pk, **values)
            )  # fmt: skip
            changes.append(f"{student}:>{values['status']}")
        elif (old.status, old.late_minutes, old.remark) != (
            values["status"], values["late_minutes"], values["remark"],
        ):  # fmt: skip
            if old.status != values["status"]:
                changes.append(f"{student}:{old.status}>{values['status']}")
            old.status, old.late_minutes, old.remark = (
                values["status"], values["late_minutes"], values["remark"],
            )  # fmt: skip
            old.updated_by = actor.pk
            old.save(update_fields=["status", "late_minutes", "remark", "updated_by", "updated_at"])
    Record.objects.bulk_create(created)
    row.version += 1
    row.updated_by = actor.pk
    row.save(update_fields=["version", "updated_by", "updated_at"])
    _audit(
        "attendance.register.saved", actor, request, row, date=row.date.isoformat(),
        changes=changes[:50], changed=len(changes), late_edit=late_edit, reason_given=bool(text),
        after_submit=row.state == Register.State.SUBMITTED,
    )  # fmt: skip
    return row


def _run_handlers(register_id: Any) -> None:
    tenant_id = str(require_tenant().id)
    for path in getattr(settings, "ATTENDANCE_SUBMITTED_HANDLERS", []):
        handler: Callable[..., Any] = import_string(path)
        transaction.on_commit(partial(handler, tenant_id=tenant_id, register_id=str(register_id)))


@transaction.atomic
def submit(
    *, actor: User, register: Register, version: int, request: HttpRequest | None = None
) -> Register:
    row = _locked_for_update(register)
    if not selectors.can_mark(actor, row):
        raise PermissionDenied("You can't take this register.")
    if row.version != version:
        raise StaleRegister(extra={"version": row.version})
    if row.state != Register.State.OPEN:
        raise ValidationError({"register": "This register is already submitted."})
    roster_ids = {p["student_id"] for p in selectors.roster(row)}
    marked = set(Record.objects.filter(register=row).values_list("student_id", flat=True))
    missing = roster_ids - marked
    if missing:
        raise ValidationError({"entries": f"{len(missing)} student(s) have no status yet."})
    row.state, row.submitted_at = Register.State.SUBMITTED, timezone.now()
    row.version += 1
    row.updated_by = actor.pk
    row.save(update_fields=["state", "submitted_at", "version", "updated_by", "updated_at"])
    absent = Record.objects.filter(register=row, status=Status.ABSENT).count()
    _audit("attendance.register.submitted", actor, request, row, date=row.date.isoformat(),
           students=len(roster_ids), absent=absent)  # fmt: skip
    _run_handlers(row.pk)
    return row


# --------------------------------------------------------------------------- lock, unlock
@transaction.atomic
def unlock(
    *, actor: User, register: Register, reason: str, request: HttpRequest | None = None
) -> Register:
    row = _locked_for_update(register)
    if not selectors.holds_at(actor, selectors.MANAGE, row.institution_id, row.campus_id):
        raise PermissionDenied("Only attendance managers can unlock registers.")
    if row.state != Register.State.LOCKED:
        raise ValidationError({"register": "This register is not locked."})
    _reason(reason, required=True)
    row.state = Register.State.SUBMITTED if row.submitted_at else Register.State.OPEN
    row.locked_at = None
    row.version += 1
    row.updated_by = actor.pk
    row.save(update_fields=["state", "locked_at", "version", "updated_by", "updated_at"])
    _audit("attendance.register.unlocked", actor, request, row, date=row.date.isoformat(),
           reason_given=True)  # fmt: skip
    return row


def lock_due(on: dt.date | None = None) -> int:
    """Lock the current tenant's registers older than their ``lock_after_days`` (P29, M5).
    Registers are grouped by institution and campus, whose settings may differ."""
    on = on or today()
    total = 0
    pairs = (
        Register.objects.exclude(state=Register.State.LOCKED)
        .values_list("institution_id", "campus_id")
        .distinct()
    )
    for institution_id, campus_id in pairs:
        days = config_for(institution_id, campus_id).lock_after_days
        total += (
            Register.objects.filter(
                institution_id=institution_id, campus_id=campus_id, date__lt=on - dt.timedelta(days)
            )
            .exclude(state=Register.State.LOCKED)
            .update(state=Register.State.LOCKED, locked_at=timezone.now())
        )
    return total
