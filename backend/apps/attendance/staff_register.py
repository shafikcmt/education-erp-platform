"""The staff daily register (Phase 8 M4; plan §5).

* **Who:** ``attendance.staff.mark`` (MFA) at the institution marks every active staff member
  there; at a campus, the staff whose home campus it is. ``attendance.staff.view`` reads the same
  scope. A staff member reads their own days with ``staff.profile.view_own``.
* **What:** one record per staff member and date (status, optional check-in and check-out times
  and a short remark), saved in one request; approved staff leave is pre-filled and never
  overwrites a saved status. Future dates are refused. Past the institution's edit window a
  reason is required (and a fresh step-up at the API).
* Audit events carry ids and statuses only; remarks and reasons are never logged.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING, Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.attendance import selectors
from apps.attendance.config import config_for
from apps.attendance.models import LeaveRequest, StaffRecord, Status
from apps.audit.services import record as audit

if TYPE_CHECKING:
    from apps.identity.models import User

MARK, VIEW = "attendance.staff.mark", "attendance.staff.view"
OWN = "staff.profile.view_own"


def staff_in_scope(actor: Any, institution_id: Any, code: str) -> QuerySet[Any]:
    """Active staff of the institution the member may see or mark with ``code``."""
    from apps.staff.models import StaffProfile
    from apps.tenancy.models import Campus

    rows = StaffProfile.objects.filter(
        institution_id=institution_id, status=StaffProfile.Status.ACTIVE
    )
    if selectors.holds_at(actor, code, institution_id):
        return rows
    campuses = [
        c
        for c in Campus.objects.filter(institution_id=institution_id).values_list("pk", flat=True)
        if selectors.holds_at(actor, code, institution_id, c)
    ]
    return rows.filter(campus_id__in=campuses) if campuses else rows.none()


def can_see(actor: Any, institution_id: Any) -> bool:
    """``attendance.staff.view`` or ``…mark`` at the institution or one of its campuses."""
    from apps.students.selectors import holds_in_institution

    return any(holds_in_institution(actor, code, institution_id) for code in (VIEW, MARK))


def register(
    actor: Any, institution_id: Any, on: dt.date, campus_id: Any = None
) -> list[dict[str, Any]]:
    """The day's staff with their saved status, approved leave or the configured default."""
    people = staff_in_scope(actor, institution_id, MARK) | staff_in_scope(
        actor, institution_id, VIEW
    )
    if campus_id is not None:
        people = people.filter(campus_id=campus_id)
    people = people.distinct().order_by("name", "number")
    ids = list(people.values_list("pk", flat=True))
    saved = {r.staff_id: r for r in StaffRecord.objects.filter(staff_id__in=ids, date=on)}
    on_leave = set(
        LeaveRequest.objects.filter(
            staff_id__in=ids, state=LeaveRequest.State.APPROVED, start_date__lte=on,
            end_date__gte=on,
        ).values_list("staff_id", flat=True)
    )  # fmt: skip
    default = config_for(institution_id).default_status
    out = []
    for person in people.values("pk", "name", "number", "campus_id"):
        row = saved.get(person["pk"])
        leave = person["pk"] in on_leave
        out.append(
            {
                "staff_id": person["pk"], "name": person["name"], "number": person["number"],
                "campus": person["campus_id"],
                "status": row.status if row else ("leave" if leave else default),
                "check_in": row.check_in if row else None,
                "check_out": row.check_out if row else None,
                "remark": row.remark if row else "",
                "status_source": "saved" if row else ("leave" if leave else "default"),
                "on_leave": leave,
            }
        )  # fmt: skip
    return out


def outside_window(institution_id: Any, on: dt.date) -> bool:
    from apps.attendance.services import today

    return on < today() - dt.timedelta(days=config_for(institution_id).edit_window_days)


def _time(value: Any, field: str) -> dt.time | None:
    if value in (None, ""):
        return None
    if isinstance(value, dt.time):
        return value
    try:
        return dt.time.fromisoformat(str(value))
    except ValueError:
        raise ValidationError({"entries": f"Invalid {field} time."}) from None


@transaction.atomic
def save(
    *,
    actor: User,
    institution: Any,
    on: dt.date,
    entries: Any,
    reason: str = "",
    request: HttpRequest | None = None,
) -> list[StaffRecord]:
    from apps.attendance.services import today

    institution_id = getattr(institution, "pk", institution)
    if on > today():
        raise ValidationError({"date": "Attendance can't be taken for a future date."})
    allowed = {
        p.pk: p
        for p in staff_in_scope(actor, institution_id, MARK)
        .select_for_update()
        .only("pk", "campus_id")
    }
    if not allowed:
        raise PermissionDenied("You can't mark the staff register here.")
    late = outside_window(institution_id, on)
    text = str(reason or "").strip()
    if late and not text:
        raise ValidationError({"reason": "Give a reason for changing an older register."})
    if len(text) > 300:
        raise ValidationError({"reason": "At most 300 characters."})
    if not isinstance(entries, list) or not entries or len(entries) > 2000:
        raise ValidationError({"entries": "Give between 1 and 2000 entries."})
    member_id = _membership(actor)
    changes: list[str] = []
    saved: list[StaffRecord] = []
    seen: set[uuid.UUID] = set()
    for item in entries:
        try:
            staff_id = uuid.UUID(str(item.get("staff")))
        except (AttributeError, ValueError):
            raise ValidationError({"entries": "Each entry names a staff member."}) from None
        if staff_id not in allowed:
            raise ValidationError({"entries": "A staff member is not on this register."})
        if staff_id in seen:
            raise ValidationError({"entries": "A staff member appears twice."})
        seen.add(staff_id)
        status = item.get("status")
        if status not in Status.values:
            raise ValidationError({"entries": "Unknown status."})
        check_in, check_out = (
            _time(item.get("check_in"), "check-in"),
            _time(item.get("check_out"), "check-out"),
        )
        if check_in and check_out and check_out <= check_in:
            raise ValidationError({"entries": "Check-out comes after check-in."})
        remark = str(item.get("remark") or "").strip()
        if len(remark) > 160:
            raise ValidationError({"entries": "Remarks are at most 160 characters."})
        values = {"status": status, "check_in": check_in, "check_out": check_out,
                  "remark": remark, "marked_by_id": member_id}  # fmt: skip
        row = StaffRecord.objects.select_for_update().filter(staff_id=staff_id, date=on).first()
        if row is None:
            try:
                with transaction.atomic():
                    row = StaffRecord.objects.create(
                        institution_id=institution_id, campus_id=allowed[staff_id].campus_id,
                        staff_id=staff_id, date=on, created_by=actor.pk, **values,
                    )  # fmt: skip
                changes.append(f"{staff_id}:>{status}")
                saved.append(row)
                continue
            except IntegrityError:  # someone saved the same day concurrently: update theirs
                row = StaffRecord.objects.select_for_update().get(staff_id=staff_id, date=on)
        if row.status != status:
            changes.append(f"{staff_id}:{row.status}>{status}")
        for key, value in values.items():
            setattr(row, key, value)
        row.updated_by = actor.pk
        row.save()
        saved.append(row)
    audit("attendance.staff.saved", actor=actor, request=request,
          target_type="tenancy.institution", target_id=institution_id,
          metadata={"date": on.isoformat(), "changes": changes[:50], "changed": len(changes),
                    "late_edit": late, "reason_given": bool(text)})  # fmt: skip
    return saved


def _membership(actor: Any) -> Any:
    from apps.students.selectors import memberships

    mine = memberships(actor)
    return mine[0] if mine else None


def my_days(actor: Any, start: dt.date, end: dt.date) -> QuerySet[StaffRecord]:
    """The member's own staff records in a date range (``staff.profile.view_own``)."""
    from apps.students.selectors import holds_anywhere, memberships

    if not holds_anywhere(actor, OWN):
        return StaffRecord.objects.none()
    return StaffRecord.objects.filter(
        staff__membership_id__in=memberships(actor), date__gte=start, date__lte=end
    ).order_by("date")
