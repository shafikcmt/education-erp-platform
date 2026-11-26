"""The staff API (Phase 7 M3; ADR-070, ADR-073): who sees which profiles (scope, campus, own),
writes by HR and administrators, structure and advisor endpoints, the module gate and another
tenant. Hidden and unknown objects both answer 404."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from apps.academics import services as academics
from apps.core.tenancy import tenant_atomic
from apps.module_registry import services as registry_services
from apps.staff import services
from apps.tenancy.models import Institution, Membership
from tests.helpers import Api, Person, make_user
from tests.isolation.factories import grant_role, seed_tenant_roles, tenant_host

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])
V1 = "/api/v1"
MODULES = ("academics", "students", "staff")


def _login(org, email: str, template: str, *, mfa: bool = True, **scope: Any):
    person = make_user(email, mfa=mfa)
    grant_role(org.tenant, person.user, template, **scope)
    api = Api(host=tenant_host(org.tenant))
    api.login(person, expect="authenticated")
    if mfa:
        api.step_up(person)
    return api, person.user


def _grant_modules(admin, tenant) -> None:
    for module in MODULES:
        registry_services.set_override(
            actor=admin.user, tenant_id=tenant.id, module_code=module, kind="grant",
            reason="Pilot agreement for staff",
        )  # fmt: skip


@pytest.fixture
def world(org, admin):
    """North: Rahim (teacher, main campus, with the fixture teacher's login), Nila (annex);
    South: Salma. A Science department and a Lecturer designation in North; a 2027 year with
    section 6A."""
    _grant_modules(admin, org.tenant)
    owner = make_user("staff-api-owner@example.com", mfa=True).user
    grant_role(org.tenant, owner, "tenant_owner")
    with tenant_atomic(org.tenant):
        Institution.objects.filter(pk=org.north.pk).update(
            preset_code="school.general.v2", preset_version="2"
        )
        science = services.create_department(
            actor=owner, institution=org.north, code="SCI", name="Science"
        )
        lecturer = services.create_designation(
            actor=owner, institution=org.north, code="LEC", name="Lecturer"
        )
        rahim = services.create_profile(
            actor=owner, institution=org.north, values={"name": "Rahim"}, number="N-1",
            campus=org.main, department=science, designation=lecturer,
            membership=Membership.objects.get(user=org.teacher),
        )  # fmt: skip
        nila = services.create_profile(
            actor=owner, institution=org.north, values={"name": "Nila"}, number="N-2",
            campus=org.annex,
        )  # fmt: skip
        salma = services.create_profile(
            actor=owner, institution=org.south, values={"name": "Salma"}, number="S-1"
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
    return {"owner": owner, "science": science, "lecturer": lecturer, "rahim": rahim,
            "nila": nila, "salma": salma, "year": year, "a": a}  # fmt: skip


def _names(api: Api) -> list[str]:
    response = api.get(f"{V1}/staff/")
    assert response.status_code == 200, response.content
    return sorted(row["name"] for row in response.json())


def test_the_module_is_required(org):
    api, _ = _login(org, "no-staff-module@example.com", "tenant_owner")
    response = api.get(f"{V1}/staff/")
    assert (response.status_code, response.json()["code"]) == (403, "module_not_entitled")


def test_each_relationship_sees_exactly_its_profiles(org, world):
    owner, _ = _login(org, "so@example.com", "tenant_owner")
    assert _names(owner) == ["Nila", "Rahim", "Salma"]
    south, _ = _login(org, "ssouth@example.com", "institution_admin", institution=org.south)
    assert _names(south) == ["Salma"]
    assert south.get(f"{V1}/staff/{world['rahim'].pk}/").status_code == 404
    campus, _ = _login(
        org, "scampus@x.example", "campus_admin", institution=org.north, campus=org.main
    )
    assert _names(campus) == ["Rahim"]  # home campus main; Nila is at the annex
    assert campus.get(f"{V1}/staff/{world['nila'].pk}/").status_code == 404
    hr, _ = _login(org, "hr@x.example", "hr_manager", institution=org.north)
    assert _names(hr) == ["Nila", "Rahim"]
    teacher = Api(host=tenant_host(org.tenant))
    teacher.login(Person(user=org.teacher), expect="authenticated")
    assert _names(teacher) == ["Rahim"]  # only their own profile
    mine = teacher.get(f"{V1}/staff/{world['rahim'].pk}/").json()
    assert (mine["relation"], mine["department_name"], mine["has_login"]) == (
        "self", "Science", True,
    )  # fmt: skip
    assert teacher.get(f"{V1}/staff/{world['nila'].pk}/").status_code == 404
    assert teacher.get(f"{V1}/staff/not-a-uuid/").status_code == 404
    assert teacher.patch(f"{V1}/staff/{world['rahim'].pk}/", {}).status_code == 403
    # Structure lists need staff.profile.view or staff.structure.manage in the institution.
    assert teacher.get(f"{V1}/staff/departments/", institution=str(org.north.pk)).status_code == 403
    listed = hr.get(f"{V1}/staff/departments/", institution=str(org.north.pk))
    assert [d["code"] for d in listed.json()] == ["SCI"]
    assert hr.get(f"{V1}/staff/designations/", institution=str(org.south.pk)).status_code == 404


def test_hr_writes_profiles_and_structure(org, world):
    hr, _ = _login(org, "hr2@x.example", "hr_manager", institution=org.north)
    dept = hr.post(
        f"{V1}/staff/departments/",
        {
            "institution": str(org.north.pk),
            "code": "ADM",
            "name": "Office",
            "kind": "administrative",
        },
    )
    assert dept.status_code == 201, dept.content
    outside = hr.post(
        f"{V1}/staff/departments/", {"institution": str(org.south.pk), "code": "X", "name": "X"}
    )
    assert outside.status_code == 404
    desig = hr.post(
        f"{V1}/staff/designations/",
        {"institution": str(org.north.pk), "code": "ACC", "name": "Accountant"},
    )
    assert desig.status_code == 201, desig.content
    created = hr.post(
        f"{V1}/staff/",
        {
            "institution": str(org.north.pk), "values": {"name": "Karim", "phone": "01711000009"},
            "number": "N-3",
            "links": {"department": dept.json()["id"], "designation": desig.json()["id"],
                      "employment_type": "contract"},
        },
    )  # fmt: skip
    assert created.status_code == 201, created.content
    body = created.json()
    assert (body["designation_name"], body["employment_type"], body["has_login"]) == (
        "Accountant", "contract", False,
    )  # fmt: skip
    changed = hr.patch(
        f"{V1}/staff/{body['id']}/", {"links": {"status": "on_leave", "department": None}}
    )
    assert changed.status_code == 200, changed.content
    assert (changed.json()["status"], changed.json()["department"]) == ("on_leave", None)
    renamed = hr.patch(f"{V1}/staff/departments/{dept.json()['id']}/", {"name": "Admin office"})
    assert renamed.json()["name"] == "Admin office"
    archived = hr.patch(f"{V1}/staff/designations/{desig.json()['id']}/", {"archived": True})
    assert archived.json()["archived"] is True
    salma = hr.post(
        f"{V1}/staff/", {"institution": str(org.south.pk), "values": {"name": "X"}, "number": "Z"}
    )
    assert salma.status_code == 404


def test_advisors_through_the_api(org, world):
    head, _ = _login(org, "nhead@x.example", "institution_admin", institution=org.north)
    body = {"year": str(world["year"].pk), "unit": str(world["a"].pk),
            "staff": str(world["rahim"].pk)}  # fmt: skip
    assigned = head.post(f"{V1}/staff/advisors/", body)
    assert assigned.status_code == 201, assigned.content
    assert (assigned.json()["unit_name"], assigned.json()["staff_name"]) == ("A", "Rahim")
    no_login = head.post(f"{V1}/staff/advisors/", {**body, "staff": str(world["nila"].pk)})
    assert no_login.status_code == 400
    listed = head.get(f"{V1}/staff/advisors/", institution=str(org.north.pk))
    assert [a["staff_name"] for a in listed.json()] == ["Rahim"]
    teacher = Api(host=tenant_host(org.tenant))
    teacher.login(Person(user=org.teacher), expect="authenticated")
    mine = teacher.get(f"{V1}/staff/{world['rahim'].pk}/").json()
    assert [a["unit_name"] for a in mine["advising"]] == ["A"]
    assert teacher.post(f"{V1}/staff/advisors/", body).status_code == 403
    advisor = assigned.json()["id"]
    assert teacher.delete(f"{V1}/staff/advisors/{advisor}/").status_code == 403
    south, _ = _login(org, "shead@x.example", "institution_admin", institution=org.south)
    assert south.delete(f"{V1}/staff/advisors/{advisor}/").status_code == 404
    assert head.delete(f"{V1}/staff/advisors/{advisor}/").status_code == 204


def test_another_tenant_sees_nothing(org, world, tenant_site, admin):
    other = tenant_site(slug="bravo")
    seed_tenant_roles(other)
    _grant_modules(admin, other)
    person = make_user("bravo-staff-owner@example.com", mfa=True)
    grant_role(other, person.user, "tenant_owner")
    api = Api(host=tenant_host(other))
    api.login(person, expect="authenticated")
    assert api.get(f"{V1}/staff/").json() == []
    assert api.get(f"{V1}/staff/{world['rahim'].pk}/").status_code == 404
    patch = api.patch(f"{V1}/staff/departments/{world['science'].pk}/", {"name": "X"})
    assert patch.status_code == 404
