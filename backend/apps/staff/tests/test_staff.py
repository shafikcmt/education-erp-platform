"""Staff: departments, designations, profiles and class-teacher advisors (Phase 7 M3; ADR-070,
ADR-073). Services, the database keys, the advisor source of "the students I teach or advise",
and tenant isolation."""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction

from apps.academics import services as academics
from apps.academics.models import AcademicYear
from apps.core.tenancy import tenant_atomic
from apps.customization import numbering
from apps.staff import services
from apps.staff.models import Department, StaffProfile, UnitAdvisor
from apps.students import selectors as student_selectors
from apps.students import services as students
from apps.tenancy.models import Institution, Membership
from tests.helpers import make_user
from tests.isolation.factories import grant_role, seed_tenant_roles

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])


@pytest.fixture
def owner(org):
    user = make_user("staff-owner@example.com", mfa=True).user
    grant_role(org.tenant, user, "tenant_owner")
    return user


@pytest.fixture
def school(org, owner):
    """North: a 2027 year, class Six (main campus) with sections A and B; students Ana in A and
    Bo in B."""
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
        ana = students.create_student(
            actor=owner, institution=org.north, values={"name": "Ana"}, number="N-1"
        )
        bo = students.create_student(
            actor=owner, institution=org.north, values={"name": "Bo"}, number="N-2"
        )
        students.enroll(actor=owner, student=ana, year=year, unit=a)
        students.enroll(actor=owner, student=bo, year=year, unit=b)
    return {"year": year, "six": six, "a": a, "b": b}


def _profile(owner, org, name="Rahim", number="T-1", **kw):
    return services.create_profile(
        actor=owner, institution=kw.pop("institution", org.north), values={"name": name},
        number=number, **kw,
    )  # fmt: skip


def test_departments_and_designations(org, owner):
    with tenant_atomic(org.tenant):
        science = services.create_department(
            actor=owner, institution=org.north, code="SCI", name="Science"
        )
        physics = services.create_department(
            actor=owner, institution=org.north, code="PHY", name="Physics", parent=science
        )
        with pytest.raises(ValidationError, match="already used"):
            services.create_department(actor=owner, institution=org.north, code="SCI", name="X")
        with pytest.raises(ValidationError, match="Use 1-32"):
            services.create_department(actor=owner, institution=org.north, code="a b", name="X")
        with pytest.raises(ValidationError, match="below itself"):
            services.update_department(
                actor=owner, department=science, changes={"parent": physics.pk}
            )
        south = services.create_department(
            actor=owner, institution=org.south, code="SCI", name="Science"
        )  # the same code in another institution is fine
        with pytest.raises(ValidationError, match="of this institution"):
            services.create_department(
                actor=owner, institution=org.north, code="CHE", name="Chemistry", parent=south
            )
        lecturer = services.create_designation(
            actor=owner, institution=org.north, code="LEC", name="Lecturer",
            name_i18n={"bn": "প্রভাষক"},
        )  # fmt: skip
        _profile(owner, org, department=physics, designation=lecturer)
        with pytest.raises(ValidationError, match="Move the department's staff"):
            services.update_department(actor=owner, department=physics, changes={"archived": True})
        archived = services.update_designation(
            actor=owner, designation=lecturer, changes={"archived": True}
        )
        assert archived.archived_at is not None
        with pytest.raises(ValidationError, match="of this institution"):
            _profile(owner, org, name="Karim", number="T-2", designation=lecturer)


def test_profiles_numbers_logins_and_scope(org, owner):
    member = make_user("rahim@example.com").user
    grant_role(org.tenant, member, "teacher", institution=org.north, campus=org.main)
    with tenant_atomic(org.tenant):
        login = Membership.objects.get(user=member)
        with pytest.raises(ValidationError, match="'staff' numbering"):
            services.create_profile(actor=owner, institution=org.north, values={"name": "A"})
        rahim = _profile(owner, org, membership=login, campus=org.main)
        assert (rahim.number, rahim.membership_id, rahim.campus_id) == (
            "T-1",
            login.pk,
            org.main.pk,
        )
        with pytest.raises(ValidationError, match="already has a profile here"):
            _profile(owner, org, name="Again", number="T-2", membership=login)
        # The same login may have a profile at another institution.
        _profile(owner, org, name="Rahim", number="S-1", institution=org.south, membership=login)
        with pytest.raises(ValidationError, match="of this institution"):
            _profile(owner, org, name="X", number="T-3", campus=org.south_main)
        numbering.define_sequence(
            actor=owner, key="staff", name="Staff", pattern="EMP-{SEQ:3}", scope="institution",
            reset="never",
        )  # fmt: skip
        auto = services.create_profile(actor=owner, institution=org.north, values={"name": "B"})
        assert auto.number == "EMP-001" and auto.membership_id is None  # no login: allowed
        with pytest.raises(ValidationError, match="Choose a value"):
            services.update_profile(actor=owner, profile=auto, links={"status": "fired"})
    head = make_user("south-head@example.com", mfa=True).user
    grant_role(org.tenant, head, "institution_admin", institution=org.south)
    with tenant_atomic(org.tenant), pytest.raises(PermissionDenied):
        services.update_profile(actor=head, profile=rahim, values={"name": "Y"})
    with tenant_atomic(org.tenant), pytest.raises(PermissionDenied):
        services.create_department(actor=org.teacher, institution=org.north, code="X", name="X")


def test_the_database_keeps_a_profile_inside_its_institution(org, owner):
    with tenant_atomic(org.tenant):
        south = services.create_department(
            actor=owner, institution=org.south, code="SCI", name="Science"
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            StaffProfile.objects.create(
                institution_id=org.north.pk, number="X", name="X", department=south
            )
        with pytest.raises(IntegrityError), transaction.atomic():
            StaffProfile.objects.create(
                institution_id=org.north.pk, number="Y", name="Y", campus_id=org.south_main.pk
            )


def test_class_teachers_see_the_students_of_the_units_they_advise(org, owner, school):
    """The advisor source (``STUDENTS_ASSIGNED_UNITS``): a campus-scoped class teacher who
    teaches nothing sees exactly the students of the section they advise."""
    adviser = make_user("adviser@example.com").user
    grant_role(org.tenant, adviser, "class_teacher", institution=org.north, campus=org.main)
    with tenant_atomic(org.tenant):
        profile = _profile(owner, org, membership=Membership.objects.get(user=adviser))
        support = _profile(owner, org, name="Guard", number="T-9")
        assert list(student_selectors.visible_students(adviser)) == []
        with pytest.raises(ValidationError, match="with a login"):
            services.assign_advisor(
                actor=owner, year=school["year"], unit=school["b"], staff=support
            )
        first = services.assign_advisor(
            actor=owner, year=school["year"], unit=school["b"], staff=profile
        )
        assert [s.name for s in student_selectors.visible_students(adviser)] == ["Bo"]
        with pytest.raises(ValidationError, match="Already an advisor"):
            services.assign_advisor(
                actor=owner, year=school["year"], unit=school["b"], staff=profile
            )
        # Advising a class covers the sections below it.
        services.assign_advisor(actor=owner, year=school["year"], unit=school["six"], staff=profile)
        names = sorted(s.name for s in student_selectors.visible_students(adviser))
        assert names == ["Ana", "Bo"]
        # A new primary advisor demotes the current one (one primary per unit and year).
        other = make_user("other-adviser@example.com").user
        grant_role(org.tenant, other, "class_teacher", institution=org.north, campus=org.main)
        second = _profile(owner, org, name="Nila", number="T-2",
                          membership=Membership.objects.get(user=other))  # fmt: skip
        services.assign_advisor(actor=owner, year=school["year"], unit=school["b"], staff=second)
        first.refresh_from_db()
        assert first.is_primary is False
        # A closed year advises nobody; leaving ends the open assignments.
        AcademicYear.objects.filter(pk=school["year"].pk).update(status="closed")
        assert list(student_selectors.visible_students(adviser)) == []
        AcademicYear.objects.filter(pk=school["year"].pk).update(status="active")
        services.update_profile(actor=owner, profile=profile, links={"status": "left"})
        assert not UnitAdvisor.objects.filter(staff=profile).exists()
        assert list(student_selectors.visible_students(adviser)) == []
    with tenant_atomic(org.tenant), pytest.raises(PermissionDenied):
        services.assign_advisor(
            actor=org.teacher, year=school["year"], unit=school["a"], staff=second
        )


def test_staff_are_invisible_to_another_tenant(org, owner, tenant_site):
    with tenant_atomic(org.tenant):
        dept = services.create_department(
            actor=owner, institution=org.north, code="SCI", name="Science"
        )
        _profile(owner, org, department=dept)
    other = tenant_site(slug="bravo")
    seed_tenant_roles(other)
    with tenant_atomic(other):
        assert not StaffProfile.objects.exists() and not Department.objects.exists()
        with connection.cursor() as cursor:
            for table in ("staff_department", "staff_designation", "staff_profile",
                          "staff_unitadvisor"):  # fmt: skip
                cursor.execute(f"SELECT count(*) FROM {table}")
                assert cursor.fetchone() == (0,)
