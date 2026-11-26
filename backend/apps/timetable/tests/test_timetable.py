"""Timetable (Phase 7 M7; ADR-071): bell schedules, rooms and slots; clash detection by the
database (unit, teacher, room) and by the service (overlapping periods of another schedule,
whole-year against term lessons); who sees which timetable; permissions and isolation."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from apps.academics import services as academics
from apps.core.tenancy import tenant_atomic
from apps.module_registry import services as registry_services
from apps.students import services as students
from apps.students.models import Guardian
from apps.tenancy.models import Institution, Membership
from apps.timetable import services
from apps.timetable.models import Slot
from tests.helpers import Api, Person, make_user
from tests.isolation.factories import grant_role, seed_tenant_roles, tenant_host

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])
V1 = "/api/v1"
T = dt.time


@pytest.fixture
def owner(org):
    user = make_user("tt-owner@example.com", mfa=True).user
    grant_role(org.tenant, user, "tenant_owner")
    return user


@pytest.fixture
def world(org, owner, admin):
    """North: 2027, Six (main) with sections A and B; Maths and English offerings; the fixture
    teacher teaches Maths in A and B, Nila teaches English in A and B. Schedule S1 (P1 08:00,
    P2 08:45, a break) and S2 (one period at 08:30, overlapping P1). Rooms R1, R2."""
    for module in ("academics", "students", "staff", "timetable"):
        registry_services.set_override(
            actor=admin.user, tenant_id=org.tenant.id, module_code=module, kind="grant",
            reason="Pilot agreement for timetable",
        )  # fmt: skip
    nila = make_user("nila-teacher@example.com").user
    grant_role(org.tenant, nila, "teacher", institution=org.north, campus=org.main)
    with tenant_atomic(org.tenant):
        Institution.objects.filter(pk=org.north.pk).update(
            preset_code="school.general.v2", preset_version="2"
        )
        year = academics.create_year(
            actor=owner, institution=org.north, code="2027", name="2027",
            start_date=dt.date(2027, 1, 1), end_date=dt.date(2027, 12, 31),
        )  # fmt: skip
        six = academics.create_unit(
            actor=owner, institution=org.north, level_key="class", code="6", name="Six",
            campus=org.main,
        )  # fmt: skip
        units = {
            x: academics.create_unit(
                actor=owner,
                institution=org.north,
                level_key="section",
                code=f"6{x}",
                name=x,
                parent=six,
                campus=org.main,
            )
            for x in "AB"
        }
        maths = academics.create_subject(actor=owner, institution=org.north, code="M", name="Maths")
        english = academics.create_subject(
            actor=owner, institution=org.north, code="E", name="English"
        )
        teacher, nila_m = (Membership.objects.get(user=u) for u in (org.teacher, nila))
        offerings: dict[str, Any] = {}
        for x, unit in units.items():
            for subject, member in ((maths, teacher), (english, nila_m)):
                offering = academics.create_offering(
                    actor=owner, year=year, unit=unit, subject=subject
                )
                academics.assign_teacher(actor=owner, offering=offering, membership=member)
                offerings[f"{subject.code}{x}"] = offering
        s1 = services.create_schedule(actor=owner, institution=org.north, code="S1", name="Day")
        p1 = services.add_period(actor=owner, schedule=s1, order=1, name="P1",
                                 start_time=T(8, 0), end_time=T(8, 45))  # fmt: skip
        p2 = services.add_period(actor=owner, schedule=s1, order=2, name="P2",
                                 start_time=T(8, 45), end_time=T(9, 30))  # fmt: skip
        brk = services.add_period(
            actor=owner, schedule=s1, order=3, name="Break", start_time=T(9, 30),
            end_time=T(9, 45), is_break=True,
        )  # fmt: skip
        s2 = services.create_schedule(actor=owner, institution=org.north, code="S2", name="Alt")
        q1 = services.add_period(actor=owner, schedule=s2, order=1, name="Q1",
                                 start_time=T(8, 30), end_time=T(9, 15))  # fmt: skip
        r1 = services.create_room(actor=owner, institution=org.north, code="R1", name="Room 1",
                                  campus=org.main, capacity=40)  # fmt: skip
        r2 = services.create_room(actor=owner, institution=org.north, code="R2", name="Room 2")
    return {"year": year, **units, **offerings, "p1": p1, "p2": p2, "break": brk, "q1": q1,
            "r1": r1, "r2": r2, "s1": s1, "nila": nila, "teacher": teacher}  # fmt: skip


def test_schedules_and_rooms_are_validated(org, owner, world):
    with tenant_atomic(org.tenant):
        with pytest.raises(ValidationError, match="don't overlap"):
            services.add_period(actor=owner, schedule=world["s1"], order=4, name="X",
                                start_time=T(8, 30), end_time=T(9, 0))  # fmt: skip
        with pytest.raises(ValidationError, match="ends after"):
            services.add_period(actor=owner, schedule=world["s1"], order=5, name="X",
                                start_time=T(11, 0), end_time=T(10, 0))  # fmt: skip
        with pytest.raises(ValidationError, match="already used"):
            services.create_room(actor=owner, institution=org.north, code="R1", name="Again")
        with pytest.raises(ValidationError, match="campus of this institution"):
            services.create_room(actor=owner, institution=org.north, code="R9", name="X",
                                 campus=org.south_main)  # fmt: skip
    with tenant_atomic(org.tenant), pytest.raises(PermissionDenied):
        services.create_room(actor=org.teacher, institution=org.north, code="R7", name="X")


def test_clashes_are_refused_by_the_service_and_the_database(org, owner, world):
    p1, r1 = world["p1"], world["r1"]
    with tenant_atomic(org.tenant):
        first = services.create_slot(actor=owner, offering=world["MA"], weekday=1, period=p1,
                                     room=r1)  # fmt: skip
        assert first.teacher_id == world["teacher"].pk  # the offering's primary teacher
        with pytest.raises(ValidationError, match="unit already has a lesson"):
            services.create_slot(actor=owner, offering=world["EA"], weekday=1, period=p1)
        with pytest.raises(ValidationError, match="teacher already teaches"):
            services.create_slot(actor=owner, offering=world["MB"], weekday=1, period=p1)
        with pytest.raises(ValidationError, match="room is already in use"):
            services.create_slot(actor=owner, offering=world["EB"], weekday=1, period=p1, room=r1)
        # Another schedule's period overlapping P1: the constraints can't see it, the service does.
        with pytest.raises(ValidationError, match="teacher already teaches"):
            services.create_slot(actor=owner, offering=world["MB"], weekday=1, period=world["q1"])
        services.create_slot(actor=owner, offering=world["MB"], weekday=1, period=world["p2"])
        services.create_slot(actor=owner, offering=world["EB"], weekday=1, period=p1,
                             room=world["r2"])  # fmt: skip
        with pytest.raises(ValidationError, match="Breaks take no lessons"):
            services.create_slot(actor=owner, offering=world["EA"], weekday=2,
                                 period=world["break"])  # fmt: skip
        with pytest.raises(ValidationError, match="teacher of this offering"):
            services.create_slot(actor=owner, offering=world["EA"], weekday=2, period=p1,
                                 teacher=world["teacher"])  # fmt: skip
        no_teacher = services.create_slot(
            actor=owner, offering=world["EA"], weekday=3, period=p1, teacher=None
        )
        assert no_teacher.teacher_id is None
        # The database itself refuses a double booking (concurrent writers).
        with pytest.raises(IntegrityError), transaction.atomic():
            Slot.objects.create(
                institution_id=org.north.pk, year=world["year"], unit=world["A"], weekday=1,
                period=p1, offering=world["EA"],
            )  # fmt: skip


def test_a_whole_year_lesson_meets_term_lessons(org, owner, world):
    with tenant_atomic(org.tenant):
        term = academics.create_term(
            actor=owner, year=world["year"], code="T1", name="Term 1",
            start_date=dt.date(2027, 1, 1), end_date=dt.date(2027, 6, 30),
        )  # fmt: skip
        art = academics.create_subject(actor=owner, institution=org.north, code="ART", name="Art")
        termly = academics.create_offering(actor=owner, year=world["year"], term=term,
                                           unit=world["A"], subject=art)  # fmt: skip
        services.create_slot(actor=owner, offering=world["MA"], weekday=4, period=world["p1"])
        with pytest.raises(ValidationError, match="unit already has a lesson"):
            services.create_slot(actor=owner, offering=termly, weekday=4, period=world["p1"],
                                 teacher=None)  # fmt: skip


def test_who_sees_which_timetable(org, owner, world, tenant_site, admin):
    with tenant_atomic(org.tenant):
        services.create_slot(actor=owner, offering=world["MA"], weekday=1, period=world["p1"],
                             room=world["r1"])  # fmt: skip
        services.create_slot(actor=owner, offering=world["EB"], weekday=1, period=world["p1"])
        ana = students.create_student(actor=owner, institution=org.north,
                                      values={"name": "Ana"}, number="N-1")  # fmt: skip
        students.enroll(actor=owner, student=ana, year=world["year"], unit=world["A"])
        link = students.link_guardian(actor=owner, student=ana,
                                      values={"name": "Rina", "phone": "01711000001"})  # fmt: skip
    head = make_user("tt-head@example.com", mfa=True)
    grant_role(org.tenant, head.user, "institution_admin", institution=org.north)
    staff = Api(host=tenant_host(org.tenant))
    staff.login(head, expect="authenticated")
    a, b = str(world["A"].pk), str(world["B"].pk)
    assert [r["subject_name"] for r in staff.get(f"{V1}/timetable/slots/", unit=a).json()] == [
        "Maths"
    ]
    by_room = staff.get(f"{V1}/timetable/slots/", room=str(world["r1"].pk)).json()
    assert [r["unit_name"] for r in by_room] == ["A"]
    teacher = Api(host=tenant_host(org.tenant))
    teacher.login(Person(user=org.teacher), expect="authenticated")
    mine = teacher.get(f"{V1}/timetable/my/").json()
    assert [(r["unit_name"], r["start_time"]) for r in mine] == [("A", "08:00:00")]
    assert (
        teacher.post(
            f"{V1}/timetable/rooms/", {"institution": str(org.north.pk), "code": "X", "name": "X"}
        ).status_code
        == 403
    )
    guardian = make_user("tt-rina@example.com")
    grant_role(org.tenant, guardian.user, "guardian")
    with tenant_atomic(org.tenant):
        Guardian.objects.filter(pk=link.guardian_id).update(
            membership=Membership.objects.get(user=guardian.user)
        )
    parent = Api(host=tenant_host(org.tenant))
    parent.login(guardian, expect="authenticated")
    assert len(parent.get(f"{V1}/timetable/slots/", unit=a).json()) == 1  # their child's unit
    assert parent.get(f"{V1}/timetable/slots/", unit=b).status_code == 404
    assert parent.get(f"{V1}/timetable/slots/", room=str(world["r1"].pk)).status_code == 404
    rooms = parent.get(f"{V1}/timetable/rooms/", institution=str(org.north.pk))
    assert rooms.status_code == 404  # staff lists only
    other = tenant_site(slug="bravo")
    seed_tenant_roles(other)
    registry_services.set_override(
        actor=admin.user, tenant_id=other.id, module_code="timetable", kind="grant",
        reason="Pilot agreement for timetable",
    )  # fmt: skip
    for module in ("academics", "staff"):
        registry_services.set_override(
            actor=admin.user, tenant_id=other.id, module_code=module, kind="grant",
            reason="Pilot agreement for timetable",
        )  # fmt: skip
    stranger = make_user("tt-bravo@example.com", mfa=True)
    grant_role(other, stranger.user, "tenant_owner")
    api = Api(host=tenant_host(other))
    api.login(stranger, expect="authenticated")
    assert api.get(f"{V1}/timetable/slots/", unit=a).status_code == 404
