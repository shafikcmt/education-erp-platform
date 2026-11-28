"""Shared attendance fixtures (Phase 8 M2-M3): a school institution with two sections, three
students, a subject teacher and a class teacher."""

from __future__ import annotations

import datetime as dt

import pytest

from apps.academics import services as academics
from apps.core.tenancy import tenant_atomic
from apps.staff import services as staff
from apps.students import services as students
from apps.tenancy.models import Institution, Membership
from tests.helpers import make_user
from tests.isolation.factories import grant_role

TODAY = dt.date.today()


@pytest.fixture
def owner_person(org):
    person = make_user("mark-owner@example.com", mfa=True)
    grant_role(org.tenant, person.user, "tenant_owner")
    return person


@pytest.fixture
def owner(owner_person):
    return owner_person.user


@pytest.fixture
def world(org, owner):
    """North (school v3, daily registers): the current year; class Six (main) with sections A
    and B; Ana and Bo in A, Cy in B; Maths in A taught by the fixture teacher; Nila is the
    class teacher (advisor) of A."""
    nila = make_user("nila-ct@example.com").user
    grant_role(org.tenant, nila, "class_teacher", institution=org.north, campus=org.main)
    with tenant_atomic(org.tenant):
        Institution.objects.filter(pk=org.north.pk).update(
            preset_code="school.general.v3", preset_version="3"
        )
        year = academics.create_year(
            actor=owner, institution=org.north, code="Y", name="Y",
            start_date=TODAY - dt.timedelta(days=200), end_date=TODAY + dt.timedelta(days=100),
        )  # fmt: skip
        six = academics.create_unit(
            actor=owner, institution=org.north, level_key="class", code="6", name="Six",
            campus=org.main,
        )  # fmt: skip
        a, b = (
            academics.create_unit(
                actor=owner,
                institution=org.north,
                level_key="section",
                code=f"6{x}",
                name=x,
                parent=six,
                campus=org.main,
            )
            for x in "AB"
        )
        maths = academics.create_subject(actor=owner, institution=org.north, code="M", name="Maths")
        offering = academics.create_offering(actor=owner, year=year, unit=a, subject=maths)
        academics.assign_teacher(
            actor=owner, offering=offering, membership=Membership.objects.get(user=org.teacher)
        )
        kids = {}
        for name, unit in (("Ana", a), ("Bo", a), ("Cy", b)):
            kids[name] = students.create_student(
                actor=owner, institution=org.north, values={"name": name}, number=f"N-{name}"
            )
            students.enroll(
                actor=owner, student=kids[name], year=year, unit=unit,
                start_date=TODAY - dt.timedelta(days=100),
            )  # fmt: skip
        profile = staff.create_profile(
            actor=owner, institution=org.north, values={"name": "Nila"}, number="T-N",
            membership=Membership.objects.get(user=nila), campus=org.main,
        )  # fmt: skip
        staff.assign_advisor(actor=owner, year=year, unit=a, staff=profile)
    return {"year": year, "six": six, "a": a, "b": b, "offering": offering, "nila": nila, **kids}
