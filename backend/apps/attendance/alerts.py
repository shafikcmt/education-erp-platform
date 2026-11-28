"""Absence alerts and low-attendance flags (Phase 8 M5; ADR-078, ADR-081 Q5).

* **Absence alerts:** when a register is submitted, a tenant task notifies (in-app; by email too
  when ``attendance.alert_email`` is on) the guardians of each absent student who receive
  notices and have a portal login, at most once per student per day (``AbsenceAlert`` unique
  key). Nothing is sent when ``attendance.alert_guardians`` is off. A later correction to
  present sends nothing; the portal shows the current status. SMS waits for Phase 14.
* **Flags (P29, nightly):** students of open years whose percentage is below
  ``attendance.threshold_percent``, or for whom a published ``attendance.flag`` rule is true, are
  flagged; their class teachers get one in-app notification when the flag appears. A flag that
  clears is removed, so a later relapse notifies again.
"""

from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction

from apps.attendance.config import config_for
from apps.attendance.models import AbsenceAlert, Record, Register, Status, StudentFlag
from apps.attendance.stats import EMPTY, figures

logger = logging.getLogger(__name__)
FLAG_NAMESPACE = "attendance.flag"


def on_register_submitted(*, tenant_id: str, register_id: str) -> None:
    """``ATTENDANCE_SUBMITTED_HANDLERS``: queue the alerts after the submission commits."""
    from apps.attendance.tasks import send_absence_alerts

    send_absence_alerts.delay(tenant_id=tenant_id, register_id=register_id)


def send_alerts(register_id: Any) -> int:
    """Notify guardians of the register's absent students; returns the alerts created."""
    from apps.notifications_core.services import notify
    from apps.students.selectors import notice_memberships

    register = Register.objects.filter(pk=register_id).first()
    if register is None:
        return 0
    config = config_for(register.institution_id, register.campus_id)
    if not config.alert_guardians:
        return 0
    absent = list(
        Record.objects.filter(register=register, status=Status.ABSENT).values_list(
            "student_id", flat=True
        )
    )
    recipients = notice_memberships(absent)
    sent = 0
    for student in absent:
        members = recipients.get(student, [])
        try:
            with transaction.atomic():
                AbsenceAlert.objects.create(
                    institution_id=register.institution_id, student_id=student,
                    date=register.date, recipients=len(members),
                )  # fmt: skip
        except IntegrityError:
            continue  # already alerted today
        if members:
            notify(
                members, kind="attendance.absence", title="Absent today",
                body=f"Marked absent on {register.date.isoformat()}.",
                link=f"/portal/children/{student}", email=config.alert_email,
            )  # fmt: skip
        sent += 1
    return sent


# --------------------------------------------------------------------------- flags (P29)
def _rule_flags(student_contexts: dict[Any, dict[str, Any]], today: dt.date) -> set[Any]:
    from apps.customization.models import Lifecycle, RuleDefinition
    from apps.customization.registry import declared_namespaces
    from apps.customization.rules import RuleError, evaluate

    rules = list(
        RuleDefinition.objects.filter(
            namespace=FLAG_NAMESPACE, status=Lifecycle.PUBLISHED
        ).values_list("rule", flat=True)
    )
    if not rules:
        return set()
    namespace = declared_namespaces()[FLAG_NAMESPACE]
    out = set()
    for student, context in student_contexts.items():
        for rule in rules:
            try:
                if evaluate(rule, namespace, {**context, "today": today}) is True:
                    out.add(student)
                    break
            except RuleError:
                logger.warning("attendance.flag_rule_failed", extra={"student": str(student)})
    return out


def refresh_flags(today: dt.date) -> int:
    """Flag (and unflag) the current tenant's students; returns newly flagged students."""
    from apps.academics.models import AcademicYear
    from apps.notifications_core.services import notify
    from apps.staff.selectors import advisor_memberships
    from apps.students.selectors import active_enrollments

    new = 0
    years = AcademicYear.objects.exclude(status=AcademicYear.Status.CLOSED).filter(
        start_date__lte=today, end_date__gte=today
    )
    for year in years:
        enrolled = active_enrollments(year.pk)  # {student: unit}
        if not enrolled:
            continue
        threshold = Decimal(config_for(year.institution_id).threshold_percent)
        stats = figures(list(enrolled), year.start_date, today)
        contexts = {s: stats.get(s, EMPTY).context() for s in enrolled}
        by_rule = _rule_flags(contexts, today)
        flagged: dict[Any, tuple[Decimal | None, bool]] = {}
        for student in enrolled:
            pct = stats.get(student, EMPTY).percent
            low = pct is not None and pct < threshold
            if low or student in by_rule:
                flagged[student] = (pct, student in by_rule)
        existing = set(
            StudentFlag.objects.filter(year=year).values_list("student_id", flat=True)
        )  # fmt: skip
        StudentFlag.objects.filter(year=year).exclude(student_id__in=list(flagged)).delete()
        advisors = advisor_memberships(year.pk, set(enrolled.values()))  # {unit: [members]}
        for student, (pct, rule) in flagged.items():
            if student in existing:
                StudentFlag.objects.filter(year=year, student_id=student).update(
                    percent=pct, by_rule=rule
                )
                continue
            StudentFlag.objects.create(
                institution_id=year.institution_id, student_id=student, year=year,
                percent=pct, by_rule=rule, flagged_on=today,
            )  # fmt: skip
            new += 1
            members = advisors.get(enrolled[student], [])
            if members:
                notify(members, kind="attendance.flag", title="Low attendance",
                       body=f"Attendance {pct}%." if pct is not None else "Attendance rule.",
                       link=f"/students/{student}")  # fmt: skip
    return new


def nightly(today: dt.date | None = None) -> dict[str, int]:
    """P29 for the current tenant: lock old registers, then refresh flags."""
    from apps.attendance.services import lock_due
    from apps.attendance.services import today as local_today

    day = today or local_today()
    return {"locked": lock_due(day), "flagged": refresh_flags(day)}
