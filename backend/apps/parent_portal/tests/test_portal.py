"""Portal invitations and the guardian/student portal (Phase 7 M8; ADR-069, ADR-073): the
Phase 3 invitation links the new login to the guardian or student record; the portal shows
only one's children (or oneself) with their enrollment and timetable; everything else 404."""

from __future__ import annotations

import datetime as dt
import itertools

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.academics import services as academics
from apps.core.tenancy import tenant_atomic
from apps.core.tokens import hash_token
from apps.module_registry import services as registry_services
from apps.students import portal, services
from apps.students.models import Guardian, PortalInvite, Student
from apps.tenancy.models import Institution, Membership
from apps.tenancy.services import invitations
from apps.timetable import services as timetable
from tests.helpers import Api, make_user
from tests.isolation.factories import grant_role, tenant_host

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])
V1 = "/api/v1"
_COUNTER = itertools.count()


@pytest.fixture
def tokens(monkeypatch):
    """Known invitation tokens (the raw token is otherwise only in the email)."""
    issued: list[str] = []

    def fake() -> tuple[str, str]:
        raw = f"portal-token-{next(_COUNTER)}"
        issued.append(raw)
        return raw, hash_token(raw)

    monkeypatch.setattr(invitations, "generate_token", fake)
    return issued


@pytest.fixture
def world(org, admin):
    """North: Ana (with guardian Rina, email) and Bo in section 6A; a Monday lesson in 6A."""
    for module in ("academics", "students", "staff", "timetable", "parent_portal"):
        registry_services.set_override(
            actor=admin.user, tenant_id=org.tenant.id, module_code=module, kind="grant",
            reason="Pilot agreement for the portal",
        )  # fmt: skip
    head = make_user("portal-head@example.com", mfa=True).user
    grant_role(org.tenant, head, "institution_admin", institution=org.north)
    with tenant_atomic(org.tenant):
        Institution.objects.filter(pk=org.north.pk).update(
            preset_code="school.general.v2", preset_version="2"
        )
        year = academics.create_year(
            actor=head, institution=org.north, code="2027", name="2027",
            start_date=dt.date(2027, 1, 1), end_date=dt.date(2027, 12, 31),
        )  # fmt: skip
        unit = academics.create_unit(
            actor=head, institution=org.north, level_key="class", code="6", name="Six"
        )
        maths = academics.create_subject(actor=head, institution=org.north, code="M", name="Maths")
        offering = academics.create_offering(actor=head, year=year, unit=unit, subject=maths)
        schedule = timetable.create_schedule(actor=head, institution=org.north, code="S", name="S")
        period = timetable.add_period(actor=head, schedule=schedule, order=1, name="P1",
                                      start_time=dt.time(8), end_time=dt.time(8, 45))  # fmt: skip
        timetable.create_slot(actor=head, offering=offering, weekday=1, period=period, teacher=None)
        ana = services.create_student(actor=head, institution=org.north,
                                      values={"name": "Ana", "email": "ana@example.com"},
                                      number="N-1")  # fmt: skip
        bo = services.create_student(actor=head, institution=org.north, values={"name": "Bo"},
                                     number="N-2")  # fmt: skip
        for student in (ana, bo):
            services.enroll(actor=head, student=student, year=year, unit=unit)
        link = services.link_guardian(
            actor=head, student=ana, relation="mother", is_primary=True,
            values={"name": "Rina", "phone": "01711000001", "email": "rina@example.com"},
        )  # fmt: skip
        phone_only = services.link_guardian(
            actor=head, student=bo, values={"name": "Karim", "phone": "01711000002"}
        )
    return {"head": head, "ana": ana, "bo": bo, "rina": link.guardian_id,
            "karim": phone_only.guardian_id}  # fmt: skip


def test_inviting_a_guardian_links_the_login_on_acceptance(org, world, tokens):
    head = world["head"]
    with tenant_atomic(org.tenant):
        rina = Guardian.objects.get(pk=world["rina"])
        invite = portal.invite_guardian(actor=head, guardian=rina)
        assert invite.kind == "guardian" and invite.linked_at is None
        with pytest.raises(ValidationError, match="email address"):
            portal.invite_guardian(actor=head, guardian=Guardian.objects.get(pk=world["karim"]))
    with tenant_atomic(org.tenant), pytest.raises(PermissionDenied):
        portal.invite_guardian(actor=org.teacher, guardian=rina)
    person = make_user("rina@example.com")
    with tenant_atomic(org.tenant):
        membership = invitations.accept_invitation(token=tokens[0], user=person.user)
        assert Guardian.objects.get(pk=world["rina"]).membership_id == membership.pk
        assert PortalInvite.objects.get(pk=invite.pk).linked_at is not None
        with pytest.raises(ValidationError, match="already has a login"):
            portal.invite_guardian(actor=head, guardian=Guardian.objects.get(pk=world["rina"]))


def test_the_portal_shows_only_ones_children(org, world, tokens):
    head = world["head"]
    with tenant_atomic(org.tenant):
        portal.invite_guardian(actor=head, guardian=Guardian.objects.get(pk=world["rina"]))
    person = make_user("rina@example.com")
    with tenant_atomic(org.tenant):
        invitations.accept_invitation(token=tokens[0], user=person.user)
    parent = Api(host=tenant_host(org.tenant))
    parent.login(person, expect="authenticated")
    children = parent.get(f"{V1}/portal/children/")
    assert children.status_code == 200, children.content
    assert [(c["name"], c["relation"], c["current"]["unit_name"]) for c in children.json()] == [
        ("Ana", "mother", "Six"),
    ]  # fmt: skip
    detail = parent.get(f"{V1}/portal/children/{world['ana'].pk}/").json()
    assert [(lesson["subject_name"], lesson["start_time"]) for lesson in detail["timetable"]] == [
        ("Maths", "08:00:00"),
    ]  # fmt: skip
    assert parent.get(f"{V1}/portal/children/{world['bo'].pk}/").status_code == 404
    assert parent.get(f"{V1}/portal/children/not-a-uuid/").status_code == 404
    # The guardian sees their child through the students API too, never Bo.
    assert parent.get(f"{V1}/students/{world['bo'].pk}/").status_code == 404
    assert parent.get(f"{V1}/students/{world['ana'].pk}/").json()["relation"] == "guardian"


def test_students_are_invited_to_see_themselves(org, world, tokens):
    head = world["head"]
    api = Api(host=tenant_host(org.tenant))
    head_person = make_user("portal-head-2@example.com", mfa=True)
    grant_role(org.tenant, head_person.user, "institution_admin", institution=org.north)
    api.login(head_person, expect="authenticated")
    api.step_up(head_person)
    invited = api.post(f"{V1}/students/{world['ana'].pk}/invite/", {})
    assert invited.status_code == 201, invited.content
    assert api.post(f"{V1}/students/{world['bo'].pk}/invite/", {}).status_code == 400  # no email
    person = make_user("ana@example.com")
    with tenant_atomic(org.tenant):
        invitations.accept_invitation(token=tokens[0], user=person.user)
        assert Student.objects.get(pk=world["ana"].pk).membership_id == (
            Membership.objects.get(user=person.user).pk
        )
    student = Api(host=tenant_host(org.tenant))
    student.login(person, expect="authenticated")
    mine = student.get(f"{V1}/portal/children/").json()
    assert [(c["name"], c["relation"]) for c in mine] == [("Ana", "self")]
    del head


def test_the_portal_needs_its_module_and_shows_staff_nothing_extra(org, world):
    staff = Api(host=tenant_host(org.tenant))
    person = make_user("portal-owner@example.com", mfa=True)
    grant_role(org.tenant, person.user, "tenant_owner")
    staff.login(person, expect="authenticated")
    assert staff.get(f"{V1}/portal/children/").json() == []  # staff scope never applies here
    assert staff.get(f"{V1}/portal/children/{world['ana'].pk}/").status_code == 404
    teacher = Api(host=tenant_host(org.tenant))
    from tests.helpers import Person

    teacher.login(Person(user=org.teacher), expect="authenticated")
    assert teacher.get(f"{V1}/portal/children/").status_code == 403  # no portal.use
