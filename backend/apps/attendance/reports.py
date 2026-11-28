"""Attendance reports (Phase 8 M6; plan §8).

* **Student reports** need ``attendance.report.view`` and ``attendance.record.view`` (or
  ``…record.manage``) in the institution; held only at a campus, they cover that campus's
  units. **Staff reports** need ``attendance.report.view`` and ``attendance.staff.view`` (or
  ``…staff.mark``), at the institution or the staff member's campus.
* ``daily_status``: each unit's daily register for a date (taken or missing, state, absent count).
* ``unit_month``: a unit's students x days grid for a month, with each student's percentage;
  also rendered as a printable document from a ``attendance.monthly_register`` template.
* ``student_summary``: per-student figures over a date range.
* ``staff_month``: staff x days grid for a month.

Every report has a formula-safe CSV (``apps.core.spreadsheets``).
"""

from __future__ import annotations

import calendar
import datetime as dt
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q

from apps.attendance import selectors
from apps.attendance.models import ATTENDED, Record, Register, StaffRecord, Status
from apps.attendance.stats import EMPTY, figures

REPORT = "attendance.report.view"
RECORD_CODES = ("attendance.record.view", "attendance.record.manage")
STAFF_CODES = ("attendance.staff.view", "attendance.staff.mark")


def _campuses(actor: Any, institution_id: Any, codes: tuple[str, ...]) -> set[Any] | None:
    """``None`` when the report and one of ``codes`` are held at the institution (everything);
    otherwise the campuses where both are held. Refused when there are none."""
    from apps.tenancy.models import Campus

    def both(campus: Any = None) -> bool:
        return selectors.holds_at(actor, REPORT, institution_id, campus) and any(
            selectors.holds_at(actor, code, institution_id, campus) for code in codes
        )

    if both():
        return None
    campuses = {
        c
        for c in Campus.objects.filter(institution_id=institution_id).values_list("pk", flat=True)
        if both(c)
    }
    if not campuses:
        raise PermissionDenied("You can't see these attendance reports.")
    return campuses


def _month(value: str) -> tuple[dt.date, dt.date]:
    try:
        start = dt.date.fromisoformat(f"{value}-01")
    except ValueError:
        raise ValidationError({"month": "Use YYYY-MM."}) from None
    end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
    return start, end


def _day_status(statuses: set[str]) -> str:
    """One status for a day of several registers: attended beats absent beats the rest."""
    if statuses & ATTENDED:
        return (
            Status.LATE
            if Status.LATE in statuses and Status.PRESENT not in statuses
            else (Status.PRESENT)
        )
    if Status.ABSENT in statuses:
        return Status.ABSENT
    return Status.LEAVE if Status.LEAVE in statuses else Status.EXCUSED


# --------------------------------------------------------------------------- student reports
def daily_status(actor: Any, institution_id: Any, on: dt.date) -> list[dict[str, Any]]:
    from apps.academics.models import Unit
    from apps.students.selectors import active_units

    campuses = _campuses(actor, institution_id, RECORD_CODES)
    units = Unit.objects.filter(pk__in=active_units(institution_id), archived_at__isnull=True)
    if campuses is not None:
        units = units.filter(campus_id__in=campuses)
    registers = {
        r.unit_id: r
        for r in Register.objects.filter(
            institution_id=institution_id, date=on, kind=Register.Kind.DAILY
        ).annotate(
            absent=Count("records", filter=Q(records__status=Status.ABSENT)),
            marked=Count("records"),
        )
    }
    out = []
    for unit in units.order_by("code"):
        reg = registers.get(unit.pk)
        out.append(
            {
                "unit": unit.pk, "unit_name": unit.name, "register": reg.pk if reg else None,
                "state": reg.state if reg else "missing",
                "marked": getattr(reg, "marked", 0), "absent": getattr(reg, "absent", 0),
            }
        )  # fmt: skip
    return out


def _unit_in_scope(actor: Any, unit_id: Any) -> Any:
    from apps.academics.models import Unit

    unit = Unit.objects.filter(pk=unit_id).first()
    if unit is None:
        raise ValidationError({"unit": "Unknown unit."})
    campuses = _campuses(actor, unit.institution_id, RECORD_CODES)
    if campuses is not None and unit.campus_id not in campuses:
        raise PermissionDenied("You can't see this unit's attendance.")
    return unit


def unit_month(actor: Any, unit_id: Any, month: str) -> dict[str, Any]:
    from apps.academics.models import AcademicYear
    from apps.students.selectors import unit_roster

    unit = _unit_in_scope(actor, unit_id)
    start, end = _month(month)
    year = (
        AcademicYear.objects.filter(
            institution_id=unit.institution_id, start_date__lte=end, end_date__gte=start
        )
        .order_by("-start_date")
        .first()
    )
    people = unit_roster({unit.pk}, year.pk, min(end, year.end_date)) if year else []
    ids = [p["student_id"] for p in people]
    days: dict[Any, dict[dt.date, set[str]]] = {}
    rows = Record.objects.filter(
        student_id__in=ids, date__gte=start, date__lte=end, register__unit=unit
    ).values_list("student_id", "date", "status")
    for student, date, status in rows:
        days.setdefault(student, {}).setdefault(date, set()).add(status)
    dates = sorted({d for by_date in days.values() for d in by_date})
    stats = figures(ids, start, end)
    out = []
    for person in people:
        cells = {
            d.isoformat(): _day_status(s) for d, s in days.get(person["student_id"], {}).items()
        }
        pct = stats.get(person["student_id"], EMPTY).percent
        out.append({**person, "cells": cells, "percent": pct})
    return {
        "unit": unit.pk, "unit_name": unit.name, "month": start.strftime("%Y-%m"),
        "dates": [d.isoformat() for d in dates], "rows": out,
    }  # fmt: skip


def student_summary(
    actor: Any, institution_id: Any, start: dt.date, end: dt.date, unit_id: Any = None
) -> list[dict[str, Any]]:
    from apps.students.selectors import active_enrollments_in

    if end < start or (end - start).days > 366:
        raise ValidationError({"end": "Choose a range of at most one year."})
    campuses = _campuses(actor, institution_id, RECORD_CODES)
    enrolled = active_enrollments_in(institution_id, campuses, unit_id)  # [{student, name, ...}]
    stats = figures([e["student_id"] for e in enrolled], start, end)
    out = []
    for row in enrolled:
        f = stats.get(row["student_id"], EMPTY)
        out.append(
            {
                **row, "attended_days": f.attended_days, "absent_days": f.absent_days,
                "late_days": f.late_days, "not_counted_days": f.not_counted_days,
                "percent": f.percent,
            }
        )  # fmt: skip
    return out


# --------------------------------------------------------------------------- staff report
def staff_month(actor: Any, institution_id: Any, month: str) -> dict[str, Any]:
    from apps.staff.models import StaffProfile

    campuses = _campuses(actor, institution_id, STAFF_CODES)
    start, end = _month(month)
    people = StaffProfile.objects.filter(
        institution_id=institution_id, status=StaffProfile.Status.ACTIVE
    )
    if campuses is not None:
        people = people.filter(campus_id__in=campuses)
    ids = list(people.values_list("pk", flat=True))
    cells: dict[Any, dict[str, str]] = {}
    for staff_id, date, status in StaffRecord.objects.filter(
        staff_id__in=ids, date__gte=start, date__lte=end
    ).values_list("staff_id", "date", "status"):
        cells.setdefault(staff_id, {})[date.isoformat()] = status
    dates = sorted({d for c in cells.values() for d in c})
    rows = [
        {"staff_id": p["pk"], "name": p["name"], "number": p["number"],
         "cells": cells.get(p["pk"], {}),
         "absent": sum(1 for v in cells.get(p["pk"], {}).values() if v == Status.ABSENT)}
        for p in people.order_by("name").values("pk", "name", "number")
    ]  # fmt: skip
    return {"month": start.strftime("%Y-%m"), "dates": dates, "rows": rows}


# --------------------------------------------------------------------------- CSV, document
def grid_csv(report: dict[str, Any], key: str) -> str:
    from apps.core.spreadsheets import csv_text

    dates = report["dates"]
    header = ["name", "number", *dates, "percent" if key == "student_id" else "absent"]
    rows = [
        [r["name"], r["number"], *[r["cells"].get(d, "") for d in dates],
         r.get("percent") if key == "student_id" else r.get("absent")]
        for r in report["rows"]
    ]  # fmt: skip
    return csv_text(header, rows)


def summary_csv(rows: list[dict[str, Any]]) -> str:
    from apps.core.spreadsheets import csv_text

    header = ["name", "number", "unit", "attended_days", "absent_days", "late_days",
              "not_counted_days", "percent"]  # fmt: skip
    return csv_text(header, [[r.get(h) for h in header] for r in rows])


def monthly_register_document(actor: Any, unit_id: Any, month: str, template_key: str,
                              locale: str = "en") -> str:  # fmt: skip
    from apps.customization import versioning
    from apps.customization.models import TemplateDefinition
    from apps.customization.template_services import render_published

    report = unit_month(actor, unit_id, month)
    template = versioning.published(TemplateDefinition, template_key)
    if template is None or template.kind != "attendance.monthly_register":
        raise ValidationError(
            {"template": "Choose a published template of the kind attendance.monthly_register."}
        )
    data = {
        "unit": report["unit_name"], "month": report["month"], "days": report["dates"],
        "rows": [
            {"name": r["name"], "roll": r["roll_number"],
             "cells": [r["cells"].get(d, "") for d in report["dates"]],
             "percent": str(r["percent"]) if r["percent"] is not None else ""}
            for r in report["rows"]
        ],
    }  # fmt: skip
    return render_published(template_key, locale, data)["body"]
