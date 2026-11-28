"""Leave requests (Phase 8 M3; plan §6): who may request and review for students and staff;
the built-in single step and a published workflow; overlaps; cancelling; approved leave in the
register's roster; the API; visibility."""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.attendance import leave, selectors, services
from apps.attendance.models import LeaveRequest
from apps.core.tenancy import tenant_atomic
from apps.customization import services as config
from apps.customization import workflows
from apps.customization.scopes import ConfigScope
from apps.module_registry import services as registry_services
from apps.staff.models import StaffProfile
from apps.students import services as students
from apps.students.models import Guardian
from apps.tenancy.models import Membership
from tests.helpers import Api, Person, make_user
from tests.isolation.factories import grant_role, tenant_host

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])
TODAY = dt.date.today()
DAY = dt.timedelta(days=1)


@pytest.fixture
def family(org, owner, world):
    """Rina is Ana's guardian with a portal login; Bo has no login; HR manager Hasan."""
    rina = make_user("rina-guardian@example.com").user
    grant_role(org.tenant, rina, "guardian")
    hasan = make_user("hasan-hr@example.com").user
    grant_role(org.tenant, hasan, "hr_manager", institution=org.north)
    with tenant_atomic(org.tenant):
        link = students.link_guardian(
            actor=owner, student=world["Ana"], relation="mother", is_primary=True,
            values={"name": "Rina", "phone": "01711000009"},
        )  # fmt: skip
        Guardian.objects.filter(pk=link.guardian_id).update(
            membership=Membership.objects.get(user=rina)
        )
    return {"rina": rina, "hasan": hasan}


def _ask(actor, **kw):
    kw.setdefault("start_date", TODAY + DAY)
    kw.setdefault("end_date", TODAY + 2 * DAY)
    kw.setdefault("reason", "Family event")
    return leave.request_leave(actor=actor, **kw)


def test_a_guardian_requests_and_the_class_teacher_decides(org, world, family):
    w, rina, nila = world, family["rina"], world["nila"]
    with tenant_atomic(org.tenant):
        request = _ask(rina, student=w["Ana"])
        assert (request.state, request.requested_by_id) == (
            "pending", Membership.objects.get(user=rina).pk,
        )  # fmt: skip
        with pytest.raises(PermissionDenied):  # Bo is not Rina's child
            _ask(rina, student=w["Bo"])
        with pytest.raises(ValidationError, match="covers these dates"):
            _ask(rina, student=w["Ana"], start_date=TODAY + 2 * DAY, end_date=TODAY + 3 * DAY)
        with pytest.raises(ValidationError, match="ends before"):
            _ask(rina, student=w["Ana"], start_date=TODAY + 5 * DAY, end_date=TODAY + 4 * DAY)
        with pytest.raises(PermissionDenied):  # the subject teacher doesn't review leave
            leave.decide(actor=org.teacher, leave=request, approve=True)
        with pytest.raises(PermissionDenied):  # HR reviews staff leave, not students'
            leave.decide(actor=family["hasan"], leave=request, approve=True)
        assert {r.pk for r in leave.visible_leave(nila)} == {request.pk}
        assert not leave.visible_leave(org.teacher).exists()
        decided = leave.decide(actor=nila, leave=request, approve=True, note="Get well")
        assert decided.state == "approved" and decided.decided_by_id is not None
        with pytest.raises(ValidationError, match="already decided"):
            leave.decide(actor=nila, leave=decided, approve=False)
    with tenant_atomic(org.tenant):
        from apps.notifications_core.models import Notification

        assert Notification.objects.filter(membership__user=rina, kind="attendance.leave").exists()


def test_approved_leave_reaches_the_register_roster(org, world, family):
    w, nila = world, world["nila"]
    with tenant_atomic(org.tenant):
        today_leave = _ask(family["rina"], student=w["Ana"], start_date=TODAY, end_date=TODAY)
        reg = services.open_register(actor=nila, kind="daily", on=TODAY, unit=w["a"])
        assert next(p for p in selectors.roster(reg) if p["name"] == "Ana")["status"] == "present"
        leave.decide(actor=nila, leave=today_leave, approve=True)
        assert next(p for p in selectors.roster(reg) if p["name"] == "Ana")["status"] == "leave"


def test_staff_leave_and_cancelling(org, owner, world, family):
    w, nila, hasan = world, world["nila"], family["hasan"]
    with tenant_atomic(org.tenant):
        profile = StaffProfile.objects.get(number="T-N")
        mine = _ask(nila, staff=profile)  # Nila asks for her own leave
        with pytest.raises(PermissionDenied):  # nobody asks for someone else's
            _ask(org.teacher, staff=profile, start_date=TODAY + 9 * DAY, end_date=TODAY + 9 * DAY)
        with pytest.raises(PermissionDenied):  # the class teacher can't review staff leave
            leave.decide(actor=nila, leave=mine, approve=True)
        approved = leave.decide(actor=hasan, leave=mine, approve=True)
        cancelled = leave.cancel(actor=nila, leave=approved)  # it starts tomorrow
        assert cancelled.state == "cancelled"
        past = _ask(owner, student=w["Bo"], start_date=TODAY - DAY, end_date=TODAY - DAY)
        leave.decide(actor=owner, leave=past, approve=True)
        with pytest.raises(ValidationError, match="pending or future"):
            leave.cancel(actor=owner, leave=past)
        with pytest.raises(ValidationError, match="half day"):
            _ask(owner, student=w["Bo"], start_date=TODAY + 20 * DAY,
                 end_date=TODAY + 21 * DAY, half_day=True)  # fmt: skip
        with pytest.raises(ValidationError, match="in the past"):
            _ask(owner, student=w["Bo"], start_date=TODAY - 40 * DAY, end_date=TODAY - 40 * DAY)


def test_a_published_workflow_gates_the_decision(org, owner, world, family):
    spec = {
        "states": [{"key": "submitted", "labels": {"en": "Submitted"}},
                   {"key": "checked", "labels": {"en": "Checked"}, "final": True}],
        "initial": "submitted", "start_permission": "attendance.leave.request",
        "transitions": [{"key": "check", "from": ["submitted"], "to": "checked",
                         "labels": {"en": "Check"}, "permission": "attendance.leave.review"}],
    }  # fmt: skip
    with tenant_atomic(org.tenant):
        workflows.save_workflow_draft(actor=owner, key="leave_check", name="Leave check",
                                      subject="attendance.leave_request", spec=spec)  # fmt: skip
        workflows.publish_workflow(actor=owner, key="leave_check")
        scope = ConfigScope(org.north.pk)
        config.save_draft(
            actor=owner, scope=scope, data={"attendance.leave_workflow": "leave_check"}
        )
        config.publish(actor=owner, scope=scope)
        request = _ask(family["rina"], student=world["Ana"])
        assert request.workflow_instance_id is not None
        with pytest.raises(ValidationError, match="workflow first"):
            leave.decide(actor=world["nila"], leave=request, approve=True)
        workflows.transition(actor=owner, instance_id=request.workflow_instance_id,
                             transition_key="check")  # fmt: skip
        assert leave.decide(actor=world["nila"], leave=request, approve=True).state == "approved"


def test_the_leave_api(org, admin, world, family):
    for module in ("academics", "students", "staff", "attendance"):
        registry_services.set_override(
            actor=admin.user, tenant_id=org.tenant.id, module_code=module, kind="grant",
            reason="Pilot agreement for attendance",
        )  # fmt: skip
    password = "Correct-Horse-9-Battery"
    for user in (family["rina"], world["nila"], org.teacher):
        user.set_password(password)
        user.save()
    rina, nila, teacher = (Api(host=tenant_host(org.tenant)) for _ in range(3))
    rina.login(Person(user=family["rina"], password=password))
    nila.login(Person(user=world["nila"], password=password))
    teacher.login(Person(user=org.teacher, password=password))
    body = {"student": str(world["Ana"].pk), "start_date": str(TODAY + DAY),
            "end_date": str(TODAY + DAY), "reason": "Doctor"}  # fmt: skip
    made = rina.post("/api/v1/attendance/leave/", body)
    assert made.status_code == 201 and made.json()["student_name"] == "Ana", made.content
    leave_id = made.json()["id"]
    other = rina.post("/api/v1/attendance/leave/", {**body, "student": str(world["Bo"].pk)})
    assert other.status_code == 403
    assert [r["id"] for r in nila.get("/api/v1/attendance/leave/").json()] == [leave_id]
    assert teacher.get(f"/api/v1/attendance/leave/{leave_id}/").status_code == 404
    assert rina.post(f"/api/v1/attendance/leave/{leave_id}/decide/",
                     {"approve": True}).status_code == 403  # fmt: skip
    decided = nila.post(f"/api/v1/attendance/leave/{leave_id}/decide/", {"approve": False})
    assert decided.json()["state"] == "rejected", decided.content
    with tenant_atomic(org.tenant):
        assert LeaveRequest.objects.get(pk=leave_id).decided_at is not None
