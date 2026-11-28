"""Attendance reports and the portal view (Phase 8 M6; plan §8): who sees which report,
figures matching a hand-computed fixture, formula-safe CSV, the monthly register from a Studio
template, and guardians seeing only their children."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied

from apps.attendance import portal, reports, services, staff_register
from apps.core.spreadsheets import safe_cell
from apps.core.tenancy import tenant_atomic
from apps.customization import template_services
from apps.module_registry import services as registry_services
from apps.staff.models import StaffProfile
from apps.students import services as students
from apps.students.models import Guardian, Student
from apps.tenancy.models import Membership
from tests.helpers import Api, Person, make_user
from tests.isolation.factories import grant_role, tenant_host

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])
TODAY = dt.date.today()
DAY = dt.timedelta(days=1)
MONTH = TODAY.strftime("%Y-%m")


def _take(owner, w, day, statuses):
    reg = services.open_register(actor=owner, kind="daily", on=day, unit=w["a"])
    entries = [{"student": str(w[n].pk), "status": s} for n, s in statuses.items()]
    services.save(actor=owner, register=reg, version=reg.version, entries=entries,
                  reason="Back-filled")  # fmt: skip


@pytest.fixture
def taken(org, owner, world):
    """Today and (if in this month) yesterday's registers for section A."""
    with tenant_atomic(org.tenant):
        _take(owner, world, TODAY, {"Ana": "present", "Bo": "absent"})
        if (TODAY - DAY).month == TODAY.month:
            _take(owner, world, TODAY - DAY, {"Ana": "late", "Bo": "absent"})
    return world


def test_daily_status_and_who_sees_reports(org, owner, taken):
    hasan = make_user("hasan-reports@example.com").user
    grant_role(org.tenant, hasan, "hr_manager", institution=org.north)
    with tenant_atomic(org.tenant):
        rows = {r["unit_name"]: r for r in reports.daily_status(owner, org.north.pk, TODAY)}
        assert (rows["A"]["state"], rows["A"]["marked"], rows["A"]["absent"]) == ("open", 2, 1)
        assert rows["B"]["state"] == "missing"  # Cy's section has no register today
        with pytest.raises(PermissionDenied):  # teachers have no report code
            reports.daily_status(org.teacher, org.north.pk, TODAY)
        with pytest.raises(PermissionDenied):  # HR: staff reports, not students'
            reports.daily_status(hasan, org.north.pk, TODAY)
        staff_register.save(actor=owner, institution=org.north, on=TODAY,
                            entries=[{"staff": str(StaffProfile.objects.get(number="T-N").pk),
                                      "status": "absent"}])  # fmt: skip
        grid = reports.staff_month(hasan, org.north.pk, MONTH)
        nila = next(r for r in grid["rows"] if r["name"] == "Nila")
        assert nila["cells"][TODAY.isoformat()] == "absent" and nila["absent"] == 1


def test_monthly_grid_summary_and_csv(org, owner, taken):
    w = taken
    two_days = (TODAY - DAY).month == TODAY.month
    with tenant_atomic(org.tenant):
        grid = reports.unit_month(owner, w["a"].pk, MONTH)
        by_name = {r["name"]: r for r in grid["rows"]}
        assert by_name["Ana"]["cells"][TODAY.isoformat()] == "present"
        assert by_name["Bo"]["percent"] == Decimal("0.00")
        assert by_name["Ana"]["percent"] == Decimal("100.00")
        summary = {r["name"]: r for r in reports.student_summary(
            owner, org.north.pk, TODAY - 5 * DAY, TODAY)}  # fmt: skip
        assert summary["Bo"]["absent_days"] == (2 if two_days else 1)
        assert summary["Cy"]["percent"] is None  # nothing taken for section B
        Student.objects.filter(pk=w["Ana"].pk).update(name="=HYPERLINK(1)")
        text = reports.grid_csv(reports.unit_month(owner, w["a"].pk, MONTH), "student_id")
        assert "'=HYPERLINK(1)" in text and "\n=HYPERLINK" not in text
        assert safe_cell("@x") == "'@x" and safe_cell("Ana") == "Ana"


def test_the_monthly_register_document(org, owner, taken):
    content = {"en": {"body": "<h1>{{ unit }} {{ month }}</h1>{% for r in rows %}"
                              "<p>{{ r.name }} {{ r.percent }}</p>{% endfor %}"}}  # fmt: skip
    with tenant_atomic(org.tenant):
        template_services.save_template_draft(actor=owner, key="register",
                                              kind_code="attendance.monthly_register",
                                              name="Register", content=content)  # fmt: skip
        template_services.publish_template(actor=owner, key="register")
        html = reports.monthly_register_document(owner, taken["a"].pk, MONTH, "register")
        assert html.startswith(f"<h1>A {MONTH}</h1>") and "<p>Ana 100.00</p>" in html


def test_guardians_see_only_their_children(org, owner, taken):
    w = taken
    rina = make_user("rina-portal-att@example.com").user
    grant_role(org.tenant, rina, "guardian")
    with tenant_atomic(org.tenant):
        link = students.link_guardian(actor=owner, student=w["Bo"], relation="mother",
                                      values={"name": "Rina", "phone": "01711000012"})  # fmt: skip
        Guardian.objects.filter(pk=link.guardian_id).update(
            membership=Membership.objects.get(user=rina)
        )
        mine = portal.month(rina, w["Bo"].pk, MONTH)
        assert mine["days"][TODAY.isoformat()] == "absent" and mine["percent"] == Decimal("0.00")
        assert portal.month(rina, w["Ana"].pk, MONTH) is None  # not her child


def test_the_reports_api(org, admin, owner_person, taken):
    for module in ("academics", "students", "staff", "attendance"):
        registry_services.set_override(
            actor=admin.user, tenant_id=org.tenant.id, module_code=module, kind="grant",
            reason="Pilot agreement for attendance",
        )  # fmt: skip
    head = Api(host=tenant_host(org.tenant))
    head.login(owner_person, expect="authenticated")
    daily = head.get("/api/v1/attendance/reports/daily/", institution=str(org.north.pk))
    assert daily.status_code == 200 and {r["unit_name"] for r in daily.json()} == {"A", "B"}
    csv = head.get("/api/v1/attendance/reports/unit-month/", unit=str(taken["a"].pk),
                   month=MONTH, export="csv")  # fmt: skip
    assert csv["Content-Type"].startswith("text/csv") and b"Ana" in csv.content
    teacher = Api(host=tenant_host(org.tenant))
    org.teacher.set_password("Correct-Horse-9-Battery")
    org.teacher.save()
    teacher.login(Person(user=org.teacher, password="Correct-Horse-9-Battery"))
    assert teacher.get("/api/v1/attendance/reports/daily/",
                       institution=str(org.north.pk)).status_code == 403  # fmt: skip
    hidden = head.get(f"/api/v1/attendance/portal/students/{taken['Ana'].pk}/")
    assert hidden.status_code in (403, 404)  # the owner is no guardian of Ana
