"""Relationship scopes and the students API (Phase 7 M2; ADR-073): staff in their scope,
teachers only the students they teach, guardians only their own children (and only their own
guardian link), students only themselves; everything else 404; writes, guardian search and merge;
the module gate and another tenant."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from apps.academics import services as academics
from apps.core.tenancy import tenant_atomic
from apps.module_registry import services as registry_services
from apps.students import services
from apps.students.models import Guardian, Student
from apps.tenancy.models import Institution, Membership
from tests.helpers import Api, make_user
from tests.isolation.factories import grant_role, seed_tenant_roles, tenant_host

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])
V1 = "/api/v1"


def _login(org, email: str, template: str, *, mfa: bool = True, **scope: Any):
    person = make_user(email, mfa=mfa)
    grant_role(org.tenant, person.user, template, **scope)
    api = Api(host=tenant_host(org.tenant))
    api.login(person, expect="authenticated")
    if mfa:
        api.step_up(person)
    return api, person.user


def _membership(org, user) -> Any:
    with tenant_atomic(org.tenant):
        return Membership.objects.get(user=user)


@pytest.fixture
def world(org, admin):
    """North: class Six on the main campus with sections A (Ana) and B (Bo); a teacher teaches
    an offering in A only. South: Cy. Ana has two guardians, mother and father."""
    for module in ("academics", "students"):
        registry_services.set_override(
            actor=admin.user, tenant_id=org.tenant.id, module_code=module, kind="grant",
            reason="Pilot agreement for students",
        )  # fmt: skip
    owner = make_user("api-owner@example.com", mfa=True).user
    grant_role(org.tenant, owner, "tenant_owner")
    with tenant_atomic(org.tenant):
        Institution.objects.filter(pk=org.north.pk).update(
            preset_code="school.general.v2", preset_version="2"
        )
        Institution.objects.filter(pk=org.south.pk).update(
            preset_code="madrasa.general.v2", preset_version="2"
        )
        year = academics.create_year(
            actor=owner, institution=org.north, code="2027", name="2027",
            start_date=dt.date(2027, 1, 1), end_date=dt.date(2027, 12, 31),
        )  # fmt: skip
        six = academics.create_unit(
            actor=owner, institution=org.north, level_key="class", code="6", name="Six",
            campus=org.main,
        )  # fmt: skip
        a = academics.create_unit(
            actor=owner, institution=org.north, level_key="section", code="6A", name="A",
            parent=six, campus=org.main,
        )  # fmt: skip
        b = academics.create_unit(
            actor=owner, institution=org.north, level_key="section", code="6B", name="B",
            parent=six, campus=org.main,
        )  # fmt: skip
        maths = academics.create_subject(actor=owner, institution=org.north, code="M", name="Maths")
        offering = academics.create_offering(actor=owner, year=year, unit=a, subject=maths)
        academics.assign_teacher(
            actor=owner, offering=offering, membership=Membership.objects.get(user=org.teacher)
        )
        ana = services.create_student(
            actor=owner, institution=org.north, values={"name": "Ana"}, number="N-1"
        )
        bo = services.create_student(
            actor=owner, institution=org.north, values={"name": "Bo"}, number="N-2"
        )
        cy = services.create_student(
            actor=owner, institution=org.south, values={"name": "Cy"}, number="S-1"
        )
        services.enroll(actor=owner, student=ana, year=year, unit=a)
        services.enroll(actor=owner, student=bo, year=year, unit=b)
        mother = services.link_guardian(
            actor=owner, student=ana, values={"name": "Rina", "phone": "01711000001"},
            relation="mother", is_primary=True,
        )  # fmt: skip
        services.link_guardian(
            actor=owner, student=ana, values={"name": "Karim", "phone": "01711000002"},
            relation="father",
        )  # fmt: skip
    return {"owner": owner, "year": year, "a": a, "b": b, "ana": ana, "bo": bo, "cy": cy,
            "mother": mother.guardian_id}  # fmt: skip


def _names(api: Api) -> list[str]:
    response = api.get(f"{V1}/students/")
    assert response.status_code == 200, response.content
    return sorted(row["name"] for row in response.json())


def test_the_module_is_required(org):
    api, _ = _login(org, "no-module@example.com", "tenant_owner")
    response = api.get(f"{V1}/students/")
    assert (response.status_code, response.json()["code"]) == (403, "module_not_entitled")


def test_each_relationship_sees_exactly_its_students(org, world):
    owner, _ = _login(org, "o2@example.com", "tenant_owner")
    assert _names(owner) == ["Ana", "Bo", "Cy"]
    south, _ = _login(org, "south@example.com", "institution_admin", institution=org.south)
    assert _names(south) == ["Cy"]
    campus, _ = _login(
        org, "campus@x.example", "campus_admin", institution=org.north, campus=org.main
    )
    assert _names(campus) == ["Ana", "Bo"]  # enrolled in units of the main campus
    annex, _ = _login(
        org, "annex@x.example", "campus_admin", institution=org.north, campus=org.annex
    )
    assert _names(annex) == []
    teacher = Api(host=tenant_host(org.tenant))
    teacher.login(make_user_existing(org.teacher), expect="authenticated")
    assert _names(teacher) == ["Ana"]  # teaches section A only
    bo = str(world["bo"].pk)
    assert teacher.get(f"{V1}/students/{bo}/").status_code == 404
    detail = teacher.get(f"{V1}/students/{world['ana'].pk}/").json()
    assert detail["relation"] == "teacher" and detail["guardians"] == []  # no guardian.view


def make_user_existing(user):
    """The fixture's teacher (password from the shared test helper)."""
    from tests.helpers import Person

    return Person(user=user)


def test_guardians_see_only_their_children_and_their_own_link(org, world):
    guardian, user = _login(org, "rina@example.com", "guardian", mfa=False)
    with tenant_atomic(org.tenant):
        Guardian.objects.filter(pk=world["mother"]).update(
            membership=Membership.objects.get(user=user)
        )
    assert _names(guardian) == ["Ana"]
    detail = guardian.get(f"{V1}/students/{world['ana'].pk}/").json()
    assert detail["relation"] == "guardian"
    assert [g["relation"] for g in detail["guardians"]] == ["mother"]  # not the father's
    assert guardian.get(f"{V1}/students/{world['bo'].pk}/").status_code == 404
    assert guardian.patch(f"{V1}/students/{world['ana'].pk}/", {}).status_code == 403


def test_students_see_only_themselves(org, world):
    student, user = _login(org, "ana@example.com", "student", mfa=False)
    with tenant_atomic(org.tenant):
        Student.objects.filter(pk=world["ana"].pk).update(
            membership=Membership.objects.get(user=user)
        )
    assert _names(student) == ["Ana"]
    assert student.get(f"{V1}/students/{world['ana'].pk}/").json()["relation"] == "self"
    assert student.get(f"{V1}/students/{world['cy'].pk}/").status_code == 404
    assert student.get(f"{V1}/students/not-a-uuid/").status_code == 404


def test_staff_write_through_the_api(org, world):
    api, _ = _login(org, "head@x.example", "institution_admin", institution=org.north)
    created = api.post(
        f"{V1}/students/",
        {"institution": str(org.north.pk), "values": {"name": "Dee"}, "number": "N-3"},
    )
    assert created.status_code == 201, created.content
    dee = created.json()["id"]
    outside = api.post(
        f"{V1}/students/",
        {"institution": str(org.south.pk), "values": {"name": "X"}, "number": "S-9"},
    )
    assert outside.status_code == 404  # not their institution
    assert api.patch(f"{V1}/students/{dee}/", {"values": {"name": "Deena"}}).json()["name"] == (
        "Deena"
    )
    enrolled = api.post(
        f"{V1}/students/{dee}/enrollments/",
        {"year": str(world["year"].pk), "unit": str(world["b"].pk), "roll_number": "7"},
    )
    assert enrolled.status_code == 201, enrolled.content
    linked = api.post(
        f"{V1}/students/{dee}/guardians/",
        {"values": {"name": "Rina", "phone": "+8801711000001"}, "relation": "mother"},
    )
    assert linked.status_code == 201, linked.content
    found = api.get(f"{V1}/guardians/", q="01711000001").json()
    assert {g["name"] for g in found} >= {"Rina"}
    detail = api.get(f"{V1}/students/{dee}/").json()
    assert [e["unit_name"] for e in detail["enrollments"]] == ["B"]
    link = detail["guardians"][0]["id"]
    assert api.delete(f"{V1}/students/{dee}/guardians/{link}/").status_code == 204
    assert api.get(f"{V1}/students/{world['cy'].pk}/").status_code == 404


def test_guardian_search_needs_three_characters_and_merge_works(org, world):
    api, _ = _login(org, "o3@example.com", "tenant_owner")
    assert api.get(f"{V1}/guardians/", q="01").status_code == 400
    with tenant_atomic(org.tenant):
        dup = Guardian.objects.create(name="Rina (copy)", email="rina@example.com")
    merged = api.post(
        f"{V1}/guardians/merge/", {"keep": str(world["mother"]), "duplicate": str(dup.pk)}
    )
    assert merged.status_code == 200, merged.content
    assert merged.json()["email"] == "rina@example.com"


def test_another_tenant_sees_nothing(org, world, tenant_site, admin):
    other = tenant_site(slug="bravo")
    seed_tenant_roles(other)
    for module in ("academics", "students"):
        registry_services.set_override(
            actor=admin.user, tenant_id=other.id, module_code=module, kind="grant",
            reason="Pilot agreement for students",
        )  # fmt: skip
    person = make_user("bravo-owner@example.com", mfa=True)
    grant_role(other, person.user, "tenant_owner")
    api = Api(host=tenant_host(other))
    api.login(person, expect="authenticated")
    assert api.get(f"{V1}/students/").json() == []
    assert api.get(f"{V1}/students/{world['ana'].pk}/").status_code == 404
