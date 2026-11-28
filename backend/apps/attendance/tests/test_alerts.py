"""Absence alerts, figures and flags (Phase 8 M5; ADR-078): once per student per day, only to
guardians with logins who receive notices, switchable; percentages over registers taken; P29
locks and flags, class teachers told once, flags clear; ``attendance.flag`` rules; the promotion
variable; the catalogue."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from django.core.cache import cache

from apps.attendance import alerts, services, stats
from apps.attendance.models import AbsenceAlert, Register, StudentFlag
from apps.core.tenancy import tenant_atomic
from apps.core.tenancy.platform import CATALOGUE
from apps.customization import rule_services
from apps.customization import services as config
from apps.customization.scopes import ConfigScope
from apps.notifications_core.models import Notification
from apps.students import lifecycle
from apps.students import services as students
from apps.students.models import Guardian
from apps.tenancy.models import Membership
from tests.helpers import make_user
from tests.isolation.factories import grant_role

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])
TODAY = dt.date.today()
DAY = dt.timedelta(days=1)


@pytest.fixture
def rina(org, owner, world):
    """Ana's guardian with a portal login who receives notices; Bo's guardian has no login."""
    user = make_user("rina-alerts@example.com").user
    grant_role(org.tenant, user, "guardian")
    with tenant_atomic(org.tenant):
        link = students.link_guardian(actor=owner, student=world["Ana"], relation="mother",
                                      values={"name": "Rina", "phone": "01711000010"})  # fmt: skip
        Guardian.objects.filter(pk=link.guardian_id).update(
            membership=Membership.objects.get(user=user)
        )
        students.link_guardian(actor=owner, student=world["Bo"],
                               values={"name": "Karim", "phone": "01711000011"})  # fmt: skip
    return user


def _take(owner, w, day, statuses, kind="daily"):
    reg = services.open_register(actor=owner, kind=kind, on=day, unit=w["a"])
    entries = [{"student": str(w[n].pk), "status": s} for n, s in statuses.items()]
    return services.save(actor=owner, register=reg, version=reg.version, entries=entries,
                         reason="Back-filled for the test")  # fmt: skip


def _notes(user, kind):
    return Notification.objects.filter(membership__user=user, kind=kind).count()


def test_absence_alerts_once_a_day_to_guardians_with_logins(org, owner, world, rina):
    w = world
    with tenant_atomic(org.tenant):
        reg = _take(owner, w, TODAY, {"Ana": "absent", "Bo": "absent"})
        assert alerts.send_alerts(reg.pk) == 2
        assert _notes(rina, "attendance.absence") == 1
        ana_alert = AbsenceAlert.objects.get(student=w["Ana"], date=TODAY)
        assert ana_alert.recipients == 1
        assert AbsenceAlert.objects.get(student=w["Bo"], date=TODAY).recipients == 0  # no login
        assert alerts.send_alerts(reg.pk) == 0  # the same day again: nothing new
        assert _notes(rina, "attendance.absence") == 1


def test_alerts_can_be_switched_off(org, owner, world, rina):
    with tenant_atomic(org.tenant):
        scope = ConfigScope(org.north.pk)
        config.save_draft(actor=owner, scope=scope, data={"attendance.alert_guardians": False})
        config.publish(actor=owner, scope=scope)
        cache.clear()
        reg = _take(owner, world, TODAY, {"Ana": "absent"})
        assert alerts.send_alerts(reg.pk) == 0
        assert not AbsenceAlert.objects.exists()


def test_figures_count_days_of_registers_taken(org, owner, world):
    w = world
    with tenant_atomic(org.tenant):
        _take(owner, w, TODAY - 3 * DAY, {"Ana": "present", "Bo": "absent"})
        _take(owner, w, TODAY - 2 * DAY, {"Ana": "late", "Bo": "absent"})
        _take(owner, w, TODAY - DAY, {"Ana": "leave", "Bo": "present"})
        _take(owner, w, TODAY, {"Ana": "absent", "Bo": "excused"})
        got = stats.figures([w["Ana"].pk, w["Bo"].pk], TODAY - 10 * DAY, TODAY)
        ana, bo = got[w["Ana"].pk], got[w["Bo"].pk]
        assert (ana.attended_days, ana.absent_days, ana.late_days, ana.not_counted_days) == (
            2, 1, 1, 1,
        )  # fmt: skip
        assert ana.percent == Decimal("66.67") and ana.consecutive_absences == 1
        assert bo.percent == Decimal("33.33") and bo.consecutive_absences == 0
        assert stats.EMPTY.percent is None
        context = lifecycle.promotion_context(w["Ana"])  # the promotion rule variable
        assert context["attendance.percent"] == 66.67


def test_p29_locks_flags_once_and_clears(org, owner, world):
    w, nila = world, world["nila"]
    with tenant_atomic(org.tenant):
        old = services.open_register(actor=owner, kind="daily", on=TODAY - 40 * DAY, unit=w["a"])
        _take(owner, w, TODAY - 2 * DAY, {"Ana": "absent", "Bo": "present"})
        _take(owner, w, TODAY - DAY, {"Ana": "absent", "Bo": "present"})
        _take(owner, w, TODAY, {"Ana": "present", "Bo": "present"})
        result = alerts.nightly()
        assert result == {"locked": 1, "flagged": 1}
        old.refresh_from_db()
        assert old.state == Register.State.LOCKED
        flag = StudentFlag.objects.get()
        assert (flag.student_id, flag.percent) == (w["Ana"].pk, Decimal("33.33"))
        assert _notes(nila, "attendance.flag") == 1  # the class teacher of A
        assert alerts.nightly()["flagged"] == 0  # already flagged: no second notice
        assert _notes(nila, "attendance.flag") == 1
        for day in range(3, 9):  # Ana comes every day afterwards (back-filled)
            _take(owner, w, TODAY - (8 + day) * DAY, {"Ana": "present", "Bo": "present"})
        alerts.nightly()
        assert not StudentFlag.objects.exists()  # 7 of 9 days: above 75%, the flag clears


def test_a_flag_rule_flags_above_the_threshold(org, owner, world):
    w = world
    with tenant_atomic(org.tenant):
        rule_services.save_rule_draft(
            actor=owner, namespace_code="attendance.flag", key="two_in_a_row", name="Two absences",
            rule={">=": [{"var": "attendance.consecutive_absences"}, 2]},
            test_cases=[{"context": {"attendance.consecutive_absences": 2}, "expected": True}],
        )  # fmt: skip
        rule_services.publish_rule(actor=owner, key="two_in_a_row")
        for day in range(9, 1, -1):
            _take(owner, w, TODAY - day * DAY, {"Ana": "present", "Bo": "present"})
        _take(owner, w, TODAY - DAY, {"Ana": "absent", "Bo": "present"})
        _take(owner, w, TODAY, {"Ana": "absent", "Bo": "present"})
        alerts.refresh_flags(TODAY)
        flag = StudentFlag.objects.get()  # 80%: above the threshold, but the rule is true
        assert flag.student_id == w["Ana"].pk and flag.by_rule is True


def test_p29_is_catalogued():
    assert CATALOGUE["P29"].enabled and CATALOGUE["P29"].mechanisms == {"I"}
