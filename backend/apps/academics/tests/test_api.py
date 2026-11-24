"""Academics API (Phase 6 M2): module entitlement first, permissions allowed and denied, scope
filtering (another institution answers 404), the services' validation through HTTP."""

from __future__ import annotations

import pytest

from apps.core.tenancy import tenant_atomic
from apps.module_registry import services as registry_services
from apps.tenancy.models import Institution, Membership
from tests.helpers import Api, make_user
from tests.isolation.factories import grant_role, tenant_host

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])
V1 = "/api/v1/academics"


def _member(org, email, template, *, step_up=True, **scope):
    person = make_user(email, mfa=template != "teacher")
    grant_role(org.tenant, person.user, template, **scope)
    api = Api(host=tenant_host(org.tenant))
    api.login(person, expect="authenticated")
    if step_up and template != "teacher":
        api.step_up(person)
    return api


@pytest.fixture
def entitled(admin, org):
    registry_services.set_override(
        actor=admin.user,
        tenant_id=org.tenant.id,
        module_code="academics",
        kind="grant",
        reason="Pilot agreement for academics",
    )
    with tenant_atomic(org.tenant):
        Institution.objects.filter(pk=org.north.pk).update(
            preset_code="school.general.v2", preset_version="2"
        )
        Institution.objects.filter(pk=org.south.pk).update(
            preset_code="madrasa.general.v2", preset_version="2"
        )
    return org


def test_the_module_is_required_before_any_permission(org):
    owner = _member(org, "o@example.com", "tenant_owner")
    response = owner.get(f"{V1}/units/", institution=str(org.north.pk))
    assert (response.status_code, response.json()["code"]) == (403, "module_not_entitled")


def test_owner_builds_years_units_subjects_and_offerings(entitled):
    org = entitled
    owner = _member(org, "o@example.com", "tenant_owner")
    north = str(org.north.pk)
    setup = owner.get(f"{V1}/setup/", institution=north).json()
    assert setup == {
        "levels": ["class", "section"],
        "level_labels": {"class": "Class", "section": "Section"},  # the preset's terminology
        "credit_based": False,
        "semester_based": False,
        "section_enabled": True,
    }
    year = owner.post(
        f"{V1}/years/",
        {"institution": north, "code": "2027", "name": "2027", "start_date": "2027-01-01",
         "end_date": "2027-12-31"},
    )  # fmt: skip
    assert year.status_code == 201, year.content
    year_id = year.json()["id"]
    assert owner.post(f"{V1}/years/{year_id}/status/", {"status": "active"}).status_code == 200
    term = owner.post(
        f"{V1}/years/{year_id}/terms/",
        {"code": "t1", "name": "First", "start_date": "2027-01-01", "end_date": "2027-04-30"},
    )
    assert term.status_code == 201, term.content
    klass = owner.post(
        f"{V1}/units/", {"institution": north, "level_key": "class", "code": "6", "name": "Six"}
    )
    assert klass.status_code == 201, klass.content
    section = owner.post(
        f"{V1}/units/",
        {"institution": north, "level_key": "section", "code": "a", "name": "A",
         "parent": klass.json()["id"]},
    )  # fmt: skip
    assert section.status_code == 201, section.content
    bad = owner.post(f"{V1}/units/", {"institution": north, "level_key": "section", "code": "b",
                                      "name": "B"})  # fmt: skip
    assert bad.status_code == 400  # a section needs its class
    renamed = owner.patch(f"{V1}/units/{section.json()['id']}/", {"name": "Section A"})
    assert renamed.json()["name"] == "Section A"
    maths = owner.post(f"{V1}/subjects/", {"institution": north, "code": "math", "name": "Maths"})
    assert maths.status_code == 201, maths.content
    credits = owner.post(
        f"{V1}/subjects/", {"institution": north, "code": "x", "name": "X", "credits": "3.00"}
    )
    assert credits.status_code == 400  # a school does not use credits
    offering = owner.post(
        f"{V1}/offerings/",
        {"year": year_id, "unit": section.json()["id"], "subject": maths.json()["id"]},
    )
    assert offering.status_code == 201, offering.content
    with tenant_atomic(org.tenant):
        teacher = str(Membership.objects.get(user=org.teacher).pk)
    assigned = owner.post(
        f"{V1}/offerings/{offering.json()['id']}/teachers/", {"membership": teacher}
    )
    assert assigned.status_code == 201, assigned.content
    listed = owner.get(f"{V1}/offerings/", year=year_id).json()
    assert [t["membership"] for t in listed[0]["teachers"]] == [teacher]
    removed = owner.delete(
        f"{V1}/offerings/{offering.json()['id']}/teachers/{assigned.json()['id']}/"
    )
    assert removed.status_code == 204
    assert [u["code"] for u in owner.get(f"{V1}/units/", institution=north).json()] == ["6", "a"]


def test_scopes_are_enforced_and_other_institutions_answer_404(entitled):
    org = entitled
    head = _member(org, "h@example.com", "institution_admin", institution=org.north)
    north, south = str(org.north.pk), str(org.south.pk)
    assert head.get(f"{V1}/units/", institution=north).status_code == 200
    assert head.get(f"{V1}/units/", institution=south).status_code == 404
    assert head.get(f"{V1}/units/").status_code == 400  # an institution is required
    created = head.post(
        f"{V1}/units/", {"institution": south, "level_key": "marhala", "code": "m", "name": "M"}
    )
    assert created.status_code == 403
    # A teacher (campus scope) reads the structure of their institution but changes nothing.
    teacher = _member(org, "t@example.com", "teacher", institution=org.north, campus=org.main)
    assert teacher.get(f"{V1}/units/", institution=north).status_code == 200
    assert teacher.get(f"{V1}/years/", institution=north).status_code == 403  # no year view
    denied = teacher.post(
        f"{V1}/units/", {"institution": north, "level_key": "class", "code": "7", "name": "Seven"}
    )
    assert denied.status_code == 403
    # Unknown or foreign ids are 404, never 500.
    assert head.patch(f"{V1}/units/not-a-uuid/", {"name": "x"}).status_code == 404
