"""Marking attendance (Phase 8 M2; ADR-077): who may open, save and submit which register;
optimistic concurrency; the edit window, lock and unlock; the roster with approved leave; the
API with 404 for hidden registers, 409 for stale saves and step-up for manager paths."""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError

from apps.attendance import selectors, services
from apps.attendance.models import LeaveRequest, Record, Register
from apps.audit.models import AuditEvent
from apps.core.tenancy import tenant_atomic
from apps.module_registry import services as registry_services
from apps.tenancy.models import Institution
from tests.helpers import Api, Person
from tests.isolation.factories import tenant_host

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])
V1 = "/api/v1/attendance"
TODAY = dt.date.today()


def _daily(actor, unit, on=TODAY):
    return services.open_register(actor=actor, kind="daily", on=on, unit=unit)


def _all(w, status_by_name):
    return [{"student": str(w[n].pk), "status": s} for n, s in status_by_name.items()]


def test_a_class_teacher_takes_the_daily_register(org, world):
    w, nila = world, world["nila"]
    with tenant_atomic(org.tenant):
        due = selectors.due_for(nila, TODAY)
        assert [(d.kind, d.unit_name, d.register) for d in due] == [("daily", "A", None)]
        reg = _daily(nila, w["a"])
        assert _daily(nila, w["a"]).pk == reg.pk  # opening again returns the same register
        roster = selectors.roster(reg)
        assert [(p["name"], p["status"], p["status_source"]) for p in roster] == [
            ("Ana", "present", "default"), ("Bo", "present", "default"),
        ]  # fmt: skip
        reg = services.save(actor=nila, register=reg, version=1, entries=_all(w, {"Bo": "absent"}))
        assert reg.version == 2
        with pytest.raises(services.StaleRegister):  # a second tab still holds version 1
            services.save(actor=nila, register=reg, version=1, entries=_all(w, {"Bo": "present"}))
        with pytest.raises(ValidationError, match="no status"):  # Ana has no status yet
            services.submit(actor=nila, register=reg, version=2)
        with pytest.raises(ValidationError, match="not on this register"):
            services.save(actor=nila, register=reg, version=2, entries=_all(w, {"Cy": "present"}))
        reg = services.save(
            actor=nila, register=reg, version=2,
            entries=[{"student": str(w["Ana"].pk), "status": "late", "late_minutes": 10}],
        )  # fmt: skip
        reg = services.submit(actor=nila, register=reg, version=3)
        assert (reg.state, reg.version) == (Register.State.SUBMITTED, 4)
        assert dict(Record.objects.filter(register=reg).values_list("student__name", "status")) == {
            "Ana": "late", "Bo": "absent",
        }  # fmt: skip
        reg = services.save(actor=nila, register=reg, version=4, entries=_all(w, {"Bo": "present"}))
        assert reg.state == Register.State.SUBMITTED  # same-day corrections stay allowed
    with tenant_atomic(org.tenant):  # tenant audit events are visible in their tenant only
        actions = set(AuditEvent.objects.filter(target_id=reg.pk).values_list("action", flat=True))
    assert {"attendance.register.opened", "attendance.register.saved",
            "attendance.register.submitted"} <= actions  # fmt: skip


def test_who_may_open_which_register(org, owner, world):
    w, nila = world, world["nila"]
    with tenant_atomic(org.tenant):
        with pytest.raises(PermissionDenied):  # a subject teacher is not the class teacher
            _daily(org.teacher, w["a"])
        with pytest.raises(PermissionDenied):  # Nila advises A, not B
            _daily(nila, w["b"])
        with pytest.raises(ValidationError, match="daily registers only"):  # school: daily mode
            services.open_register(actor=org.teacher, kind="period", on=TODAY,
                                   offering=w["offering"])  # fmt: skip
        assert _daily(owner, w["b"]).unit_id == w["b"].pk  # attendance.record.manage: any register
        with pytest.raises(ValidationError, match="future"):
            _daily(nila, w["a"], TODAY + dt.timedelta(days=1))
        with pytest.raises(ValidationError, match="open academic year"):
            _daily(owner, w["a"], TODAY - dt.timedelta(days=400))
        with pytest.raises(ValidationError, match="units students sit in"):
            _daily(owner, w["six"])
        assert selectors.visible_register(org.teacher, _daily(nila, w["a"]).pk) is None


def test_period_registers_follow_the_offering(org, world):
    w, nila = world, world["nila"]
    with tenant_atomic(org.tenant):
        Institution.objects.filter(pk=org.north.pk).update(
            preset_code="university.credit.v3", preset_version="3"
        )
        cache.clear()  # resolved configuration is cached; a real preset change publishes
        due = selectors.due_for(org.teacher, TODAY)
        assert [(d.kind, d.subject_name) for d in due] == [("period", "Maths")]
        first = services.open_register(actor=org.teacher, kind="period", on=TODAY,
                                       offering=w["offering"])  # fmt: skip
        second = services.open_register(actor=org.teacher, kind="period", on=TODAY,
                                        offering=w["offering"], sequence=2)  # fmt: skip
        assert first.pk != second.pk and first.unit_id == w["a"].pk
        with pytest.raises(PermissionDenied):  # Nila doesn't teach Maths
            services.open_register(actor=nila, kind="period", on=TODAY, offering=w["offering"])
        with pytest.raises(ValidationError, match="period registers only"):
            _daily(nila, w["a"])
        assert [p["name"] for p in selectors.roster(first)] == ["Ana", "Bo"]


def test_the_edit_window_lock_and_unlock(org, owner, world):
    w, nila = world, world["nila"]
    with tenant_atomic(org.tenant):
        old = _daily(owner, w["a"], TODAY - dt.timedelta(days=5))
        with pytest.raises(PermissionDenied, match="older registers"):  # 5 days > 3-day window
            services.save(actor=nila, register=old, version=1, entries=_all(w, {"Ana": "absent"}))
        with pytest.raises(ValidationError, match="reason"):
            services.save(actor=owner, register=old, version=1, entries=_all(w, {"Ana": "absent"}))
        old = services.save(actor=owner, register=old, version=1,
                            entries=_all(w, {"Ana": "absent"}), reason="Late register")  # fmt: skip
        ancient = _daily(owner, w["a"], TODAY - dt.timedelta(days=40))
        assert services.lock_due() == 1  # only the 40-day-old one (lock after 30 days)
        ancient.refresh_from_db()
        assert ancient.state == Register.State.LOCKED and ancient.locked_at is not None
        with pytest.raises(ValidationError, match="locked"):
            services.save(actor=owner, register=ancient, version=1,
                          entries=_all(w, {"Ana": "absent"}), reason="x")  # fmt: skip
        with pytest.raises(PermissionDenied):
            services.unlock(actor=nila, register=ancient, reason="please")
        with pytest.raises(ValidationError, match="reason"):
            services.unlock(actor=owner, register=ancient, reason=" ")
        ancient = services.unlock(actor=owner, register=ancient, reason="Correction ordered")
        assert (ancient.state, ancient.version) == (Register.State.OPEN, 2)
    with tenant_atomic(org.tenant):
        event = AuditEvent.objects.get(action="attendance.register.saved", target_id=old.pk)
    assert event.metadata["late_edit"] is True and event.metadata["reason_given"] is True
    assert "Late register" not in str(event.metadata)  # free text stays out of the audit log


def test_approved_leave_is_pre_filled_but_never_overwrites(org, owner, world):
    w, nila = world, world["nila"]
    with tenant_atomic(org.tenant):
        LeaveRequest.objects.create(
            institution_id=org.north.pk, student=w["Ana"], start_date=TODAY, end_date=TODAY,
            reason="Fever", state=LeaveRequest.State.APPROVED,
        )  # fmt: skip
        LeaveRequest.objects.create(
            institution_id=org.north.pk, student=w["Bo"], start_date=TODAY, end_date=TODAY,
            reason="Trip", state=LeaveRequest.State.PENDING,
        )  # fmt: skip
        reg = _daily(nila, w["a"])
        roster = {p["name"]: (p["status"], p["status_source"]) for p in selectors.roster(reg)}
        assert roster == {"Ana": ("leave", "leave"), "Bo": ("present", "default")}
        services.save(actor=nila, register=reg, version=1, entries=_all(w, {"Ana": "present"}))
        ana = next(p for p in selectors.roster(reg) if p["name"] == "Ana")
        assert (ana["status"], ana["status_source"], ana["on_leave"]) == ("present", "saved", True)


def test_the_marking_api(org, owner_person, admin, world):
    w = world
    registry_services.set_override(
        actor=admin.user, tenant_id=org.tenant.id, module_code="attendance", kind="grant",
        reason="Pilot agreement for attendance",
    )  # fmt: skip
    for module in ("academics", "students", "staff"):
        registry_services.set_override(
            actor=admin.user, tenant_id=org.tenant.id, module_code=module, kind="grant",
            reason="Pilot agreement for attendance",
        )  # fmt: skip
    nila = Api(host=tenant_host(org.tenant))
    w["nila"].set_password("Correct-Horse-9-Battery")
    w["nila"].save()
    nila.login(Person(user=w["nila"], password="Correct-Horse-9-Battery"))
    due = nila.get(f"{V1}/due/")
    assert [d["unit_name"] for d in due.json()] == ["A"], due.content
    opened = nila.post(f"{V1}/registers/", {"kind": "daily", "date": str(TODAY),
                                            "unit": str(w["a"].pk)})  # fmt: skip
    assert opened.status_code == 201, opened.content
    body = opened.json()
    reg_id, version = body["register"]["id"], body["register"]["version"]
    assert [r["name"] for r in body["roster"]] == ["Ana", "Bo"] and body["can_mark"] is True
    entries = [{"student": str(w["Ana"].pk), "status": "absent"},
               {"student": str(w["Bo"].pk), "status": "present"}]  # fmt: skip
    saved = nila.post(f"{V1}/registers/{reg_id}/save/", {"version": version, "entries": entries})
    assert saved.status_code == 200 and saved.json()["register"]["version"] == version + 1
    stale = nila.post(f"{V1}/registers/{reg_id}/save/", {"version": version, "entries": entries})
    assert stale.status_code == 409 and stale.json()["code"] == "stale_register", stale.content
    submitted = nila.post(f"{V1}/registers/{reg_id}/submit/", {"version": version + 1})
    assert submitted.json()["register"]["state"] == "submitted", submitted.content
    listed = nila.get(f"{V1}/registers/", institution=str(org.north.pk), date=str(TODAY))
    assert [r["id"] for r in listed.json()] == [reg_id]
    # The subject teacher neither sees nor marks the class teacher's register.
    teacher = Api(host=tenant_host(org.tenant))
    org.teacher.set_password("Correct-Horse-9-Battery")
    org.teacher.save()
    teacher.login(Person(user=org.teacher, password="Correct-Horse-9-Battery"))
    assert teacher.get(f"{V1}/registers/{reg_id}/").status_code == 404
    assert teacher.post(f"{V1}/registers/{reg_id}/save/",
                        {"version": 3, "entries": entries}).status_code == 404  # fmt: skip
    assert teacher.get(f"{V1}/registers/", institution=str(org.south.pk)).status_code == 404
    # Unlocking needs the manager code, MFA and a fresh step-up.
    with tenant_atomic(org.tenant):
        Register.objects.filter(pk=reg_id).update(state=Register.State.LOCKED)
    assert nila.post(f"{V1}/registers/{reg_id}/unlock/", {"reason": "x"}).status_code == 403
    head = Api(host=tenant_host(org.tenant))
    head.login(owner_person, expect="authenticated")
    no_step_up = head.post(f"{V1}/registers/{reg_id}/unlock/", {"reason": "Correction"})
    assert no_step_up.status_code == 403 and no_step_up.json()["code"] == "step_up_required"
    head.step_up(owner_person)
    unlocked = head.post(f"{V1}/registers/{reg_id}/unlock/", {"reason": "Correction"})
    assert unlocked.json()["register"]["state"] == "submitted", unlocked.content
