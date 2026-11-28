"""The staff daily register (Phase 8 M4; plan §5): campus and institution scopes, check-in and
check-out, approved staff leave pre-filled, the edit window, one's own days, the API."""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.attendance import leave, staff_register
from apps.attendance.models import StaffRecord
from apps.audit.models import AuditEvent
from apps.core.tenancy import tenant_atomic
from apps.module_registry import services as registry_services
from apps.staff import services as staff
from apps.staff.models import StaffProfile
from tests.helpers import Api, Person, make_user
from tests.isolation.factories import grant_role, tenant_host

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])
TODAY = dt.date.today()


@pytest.fixture
def team(org, owner, world):
    """Nila (main campus, from ``world``), Omar (annex), Sami (no campus); Faria at the main
    campus front desk; Hasan in HR for the institution."""
    faria = make_user("faria-desk@example.com", mfa=True)
    grant_role(org.tenant, faria.user, "front_desk", institution=org.north, campus=org.main)
    hasan = make_user("hasan-hr2@example.com", mfa=True)
    grant_role(org.tenant, hasan.user, "hr_manager", institution=org.north)
    with tenant_atomic(org.tenant):
        omar = staff.create_profile(actor=owner, institution=org.north, values={"name": "Omar"},
                                    number="T-O", campus=org.annex)  # fmt: skip
        sami = staff.create_profile(actor=owner, institution=org.north, values={"name": "Sami"},
                                    number="T-S")  # fmt: skip
        nila = StaffProfile.objects.get(number="T-N")
    return {"faria": faria, "hasan": hasan, "omar": omar, "sami": sami, "nila": nila}


def _names(rows):
    return [r["name"] for r in rows]


def test_scopes_and_saving(org, team):
    t = team
    with tenant_atomic(org.tenant):
        assert _names(staff_register.register(t["faria"].user, org.north.pk, TODAY)) == ["Nila"]
        assert _names(staff_register.register(t["hasan"].user, org.north.pk, TODAY)) == [
            "Nila", "Omar", "Sami",
        ]  # fmt: skip
        staff_register.save(
            actor=t["faria"].user, institution=org.north, on=TODAY,
            entries=[{"staff": str(t["nila"].pk), "status": "late", "check_in": "08:40",
                      "check_out": "14:00"}],
        )  # fmt: skip
        with pytest.raises(ValidationError, match="not on this register"):  # Omar is at the annex
            staff_register.save(
                actor=t["faria"].user,
                institution=org.north,
                on=TODAY,
                entries=[{"staff": str(t["omar"].pk), "status": "present"}],
            )
        with pytest.raises(PermissionDenied):
            staff_register.save(
                actor=org.teacher,
                institution=org.north,
                on=TODAY,
                entries=[{"staff": str(t["nila"].pk), "status": "present"}],
            )
        with pytest.raises(ValidationError, match="after check-in"):
            staff_register.save(
                actor=t["hasan"].user, institution=org.north, on=TODAY,
                entries=[{"staff": str(t["sami"].pk), "status": "present", "check_in": "09:00",
                          "check_out": "08:00"}],
            )  # fmt: skip
        with pytest.raises(ValidationError, match="future"):
            staff_register.save(
                actor=t["hasan"].user,
                institution=org.north,
                on=TODAY + dt.timedelta(days=1),
                entries=[{"staff": str(t["sami"].pk), "status": "present"}],
            )
        # Saving again updates the same day (one record per staff member and date).
        staff_register.save(
            actor=t["hasan"].user,
            institution=org.north,
            on=TODAY,
            entries=[{"staff": str(t["nila"].pk), "status": "present"}],
        )
        row = StaffRecord.objects.get(staff=t["nila"], date=TODAY)
        assert (row.status, row.check_in, row.campus_id) == ("present", None, org.main.pk)
        event = AuditEvent.objects.filter(action="attendance.staff.saved").order_by("-occurred_at")[
            0
        ]
        assert event.metadata["changes"] == [f"{t['nila'].pk}:late>present"]


def test_leave_is_pre_filled_and_old_days_need_a_reason(org, team):
    t = team
    with tenant_atomic(org.tenant):
        request = leave.request_leave(actor=t["hasan"].user, staff=t["sami"], start_date=TODAY,
                                      end_date=TODAY, reason="Medical")  # fmt: skip
        leave.decide(actor=t["hasan"].user, leave=request, approve=True)
        rows = {r["name"]: r for r in staff_register.register(t["hasan"].user, org.north.pk, TODAY)}
        assert (rows["Sami"]["status"], rows["Sami"]["status_source"]) == ("leave", "leave")
        old = TODAY - dt.timedelta(days=10)
        with pytest.raises(ValidationError, match="reason"):
            staff_register.save(
                actor=t["hasan"].user,
                institution=org.north,
                on=old,
                entries=[{"staff": str(t["sami"].pk), "status": "absent"}],
            )
        staff_register.save(
            actor=t["hasan"].user,
            institution=org.north,
            on=old,
            entries=[{"staff": str(t["sami"].pk), "status": "absent"}],
            reason="Register found late",
        )


def test_own_days_and_the_api(org, admin, team, world):
    t = team
    for module in ("academics", "students", "staff", "attendance"):
        registry_services.set_override(
            actor=admin.user, tenant_id=org.tenant.id, module_code=module, kind="grant",
            reason="Pilot agreement for attendance",
        )  # fmt: skip
    with tenant_atomic(org.tenant):
        staff_register.save(
            actor=t["hasan"].user,
            institution=org.north,
            on=TODAY,
            entries=[{"staff": str(t["nila"].pk), "status": "absent"}],
        )
        mine = staff_register.my_days(world["nila"], TODAY - dt.timedelta(days=1), TODAY)
        assert [(r.date, r.status) for r in mine] == [(TODAY, "absent")]
        assert not staff_register.my_days(org.teacher, TODAY, TODAY).exists()  # no profile
    desk = Api(host=tenant_host(org.tenant))
    desk.login(t["faria"], expect="authenticated")
    got = desk.get("/api/v1/attendance/staff/register/", institution=str(org.north.pk))
    assert got.status_code == 200 and _names(got.json()["rows"]) == ["Nila"], got.content
    saved = desk.post("/api/v1/attendance/staff/register/save/", {
        "institution": str(org.north.pk), "date": str(TODAY),
        "entries": [{"staff": str(t["nila"].pk), "status": "present", "check_in": "08:00"}],
    })  # fmt: skip
    assert saved.status_code == 200 and saved.json()["rows"][0]["status"] == "present"
    old = desk.post("/api/v1/attendance/staff/register/save/", {
        "institution": str(org.north.pk), "date": str(TODAY - dt.timedelta(days=9)),
        "entries": [{"staff": str(t["nila"].pk), "status": "present"}], "reason": "Late",
    })  # fmt: skip
    assert old.status_code == 403 and old.json()["code"] == "step_up_required"
    assert desk.get("/api/v1/attendance/staff/register/",
                    institution=str(org.south.pk)).status_code == 404  # fmt: skip
    nila = Api(host=tenant_host(org.tenant))
    world["nila"].set_password("Correct-Horse-9-Battery")
    world["nila"].save()
    nila.login(Person(user=world["nila"], password="Correct-Horse-9-Battery"))
    days = nila.get("/api/v1/attendance/staff/mine/")
    assert [d["status"] for d in days.json()] == ["present"], days.content
