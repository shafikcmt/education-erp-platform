"""Students, guardians and enrollments (Phase 7 M1; ADR-068, ADR-074): numbering, custom
fields, the plan limit, guardian matching within the tenant and merging, enrollment rules,
permissions in the institution scope, composite keys and tenant isolation."""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction

from apps.academics import services as academics
from apps.academics.models import AcademicYear
from apps.core.tenancy import tenant_atomic
from apps.customization import fields, numbering
from apps.students import services
from apps.students.models import Enrollment, Guardian, Student, StudentGuardian
from apps.tenancy.models import Institution
from tests.helpers import make_user
from tests.isolation.factories import grant_role, seed_tenant_roles

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])


@pytest.fixture
def owner(org):
    user = make_user("students-owner@example.com", mfa=True).user
    grant_role(org.tenant, user, "tenant_owner")
    return user


@pytest.fixture
def school(org, owner):
    """North (school preset v2): a 2027 year, class Six with sections A and B; South (madrasa)
    with a year and a jamaat."""
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
            actor=owner, institution=org.north, level_key="class", code="6", name="Six"
        )
        a = academics.create_unit(
            actor=owner, institution=org.north, level_key="section", code="6A", name="A",
            parent=six,
        )  # fmt: skip
        b = academics.create_unit(
            actor=owner, institution=org.north, level_key="section", code="6B", name="B",
            parent=six,
        )  # fmt: skip
        south_year = academics.create_year(
            actor=owner, institution=org.south, code="1448", name="1448",
            start_date=dt.date(2027, 1, 1), end_date=dt.date(2027, 12, 31),
        )  # fmt: skip
        marhala = academics.create_unit(
            actor=owner, institution=org.south, level_key="marhala", code="m1", name="M1"
        )
        jamaat = academics.create_unit(
            actor=owner, institution=org.south, level_key="jamaat", code="j1", name="J1",
            parent=marhala,
        )  # fmt: skip
    return {"year": year, "six": six, "a": a, "b": b, "south_year": south_year, "jamaat": jamaat}


def _student(owner, org, name="Ana", number="S-1", **kw):
    return services.create_student(
        actor=owner, institution=org.north, values={"name": name, **kw}, number=number
    )


def test_numbers_come_from_the_student_sequence_or_are_given(org, owner):
    with tenant_atomic(org.tenant):
        with pytest.raises(ValidationError, match="student' numbering"):
            services.create_student(actor=owner, institution=org.north, values={"name": "Ana"})
        manual = _student(owner, org, number="2027-001")
        with pytest.raises(ValidationError, match="already used"):
            _student(owner, org, name="Bo", number="2027-001")
        with pytest.raises(ValidationError, match="Use letters"):
            _student(owner, org, name="Bo", number="bad number!")
        numbering.define_sequence(
            actor=owner, key="student", name="Students", pattern="STU-{SEQ:4}",
            scope="institution", reset="never",
        )  # fmt: skip
        first = services.create_student(actor=owner, institution=org.north, values={"name": "Cy"})
        second = services.create_student(actor=owner, institution=org.north, values={"name": "Di"})
        assert (manual.number, first.number, second.number) == ("2027-001", "STU-0001", "STU-0002")
        with pytest.raises(ValidationError, match="name"):
            services.create_student(actor=owner, institution=org.north, values={"name": " "})
        with pytest.raises(ValidationError, match="future"):
            _student(owner, org, name="Ed", number="x1", date_of_birth="2999-01-01")
        with pytest.raises(ValidationError, match="Unknown field"):
            _student(owner, org, name="Ed", number="x1", nickname="E")


def test_custom_fields_are_validated_and_the_plan_limit_is_enforced(org, owner, settings):
    with tenant_atomic(org.tenant):
        fields.define_field(
            actor=owner, entity="students.student", key="blood_group", field_type="text",
            labels={"en": "Blood group"},
        )  # fmt: skip
        with pytest.raises(ValidationError, match="Unknown field"):
            services.create_student(
                actor=owner, institution=org.north, values={"name": "Ana"}, number="1",
                extra={"shoe_size": 40},
            )  # fmt: skip
        ana = services.create_student(
            actor=owner, institution=org.north, values={"name": "Ana"}, number="1",
            extra={"blood_group": "O+"},
        )  # fmt: skip
        assert ana.extra == {"blood_group": "O+"}
        updated = services.update_student(actor=owner, student=ana, extra={"blood_group": "A+"})
        assert updated.extra == {"blood_group": "A+"}
        settings.STUDIO_QUOTA_DEFAULTS = {
            **settings.STUDIO_QUOTA_DEFAULTS,
            "max_active_students": 2,
        }
        _student(owner, org, name="Bo", number="2")
        with pytest.raises(ValidationError, match="allows 2 active students"):
            _student(owner, org, name="Cy", number="3")


def test_guardians_are_matched_within_the_tenant_and_linked_once(org, owner, school):
    with tenant_atomic(org.tenant):
        ana = _student(owner, org)
        bo = services.create_student(
            actor=owner, institution=org.south, values={"name": "Bo"}, number="S-1"
        )
        with pytest.raises(ValidationError, match="phone number or an email"):
            services.link_guardian(actor=owner, student=ana, values={"name": "Rina"})
        with pytest.raises(ValidationError, match="relation"):
            services.link_guardian(
                actor=owner, student=ana, values={"name": "Rina", "phone": "01711-000000"},
                relation="boss",
            )  # fmt: skip
        first = services.link_guardian(
            actor=owner, student=ana, values={"name": "Rina", "phone": "01711-000000"},
            relation="mother", is_primary=True,
        )  # fmt: skip
        # The same phone written differently, for a child in another institution: same guardian.
        second = services.link_guardian(
            actor=owner, student=bo, values={"name": "Rina B", "phone": "01711 000 000"},
            relation="mother",
        )  # fmt: skip
        assert first.guardian_id == second.guardian_id and Guardian.objects.count() == 1
        assert Guardian.objects.get().phone == "01711000000"
        with pytest.raises(ValidationError, match="already linked"):
            services.link_guardian(
                actor=owner, student=ana, values={"phone": "01711000000"}, relation="mother"
            )
        father = services.link_guardian(
            actor=owner, student=ana, values={"name": "Karim", "email": "Karim@Example.com"},
            relation="father", is_primary=True,
        )  # fmt: skip
        primaries = StudentGuardian.objects.filter(student=ana, is_primary=True)
        assert list(primaries.values_list("pk", flat=True)) == [father.pk]  # one primary
        assert Guardian.objects.get(pk=father.guardian_id).email == "karim@example.com"


def test_duplicate_guardians_are_merged(org, owner):
    with tenant_atomic(org.tenant):
        ana, bo = _student(owner, org), _student(owner, org, name="Bo", number="S-2")
        by_phone = Guardian.objects.get(pk=services.link_guardian(
            actor=owner, student=ana, values={"name": "Rina", "phone": "01711000000"},
            relation="mother",
        ).guardian_id)  # fmt: skip
        by_email = Guardian.objects.get(pk=services.link_guardian(
            actor=owner, student=bo, values={"name": "Rina", "email": "rina@example.com"},
            relation="mother",
        ).guardian_id)  # fmt: skip
        services.link_guardian(actor=owner, student=ana, guardian=by_email, relation="mother")
        kept = services.merge_guardians(actor=owner, keep=by_phone, duplicate=by_email)
        assert (kept.phone, kept.email) == ("01711000000", "rina@example.com")
        assert not Guardian.objects.filter(pk=by_email.pk).exists()
        assert sorted(StudentGuardian.objects.values_list("student__name", flat=True)) == [
            "Ana", "Bo",
        ]  # fmt: skip
        with pytest.raises(ValidationError, match="two different"):
            services.merge_guardians(actor=owner, keep=kept, duplicate=kept)


def test_enrollment_rules(org, owner, school):
    with tenant_atomic(org.tenant):
        ana = _student(owner, org)
        with pytest.raises(ValidationError, match="units below it"):
            services.enroll(actor=owner, student=ana, year=school["year"], unit=school["six"])
        with pytest.raises(ValidationError, match="unit of this institution"):
            services.enroll(actor=owner, student=ana, year=school["year"], unit=school["jamaat"])
        with pytest.raises(ValidationError, match="open academic year"):
            services.enroll(actor=owner, student=ana, year=school["south_year"], unit=school["a"])
        row = services.enroll(
            actor=owner, student=ana, year=school["year"], unit=school["a"], roll_number="1"
        )
        assert (row.status, row.start_date) == ("active", dt.date(2027, 1, 1))
        with pytest.raises(ValidationError, match="already enrolled"):
            services.enroll(actor=owner, student=ana, year=school["year"], unit=school["b"])
        bo = _student(owner, org, name="Bo", number="S-2")
        with pytest.raises(ValidationError, match="roll number"):
            services.enroll(
                actor=owner, student=bo, year=school["year"], unit=school["a"], roll_number="1"
            )
        AcademicYear.objects.filter(pk=school["year"].pk).update(status="closed")
        with pytest.raises(ValidationError, match="open academic year"):
            services.enroll(actor=owner, student=bo, year=school["year"], unit=school["b"])


def test_the_database_keeps_an_enrollment_inside_its_institution(org, owner, school):
    with tenant_atomic(org.tenant):
        ana = _student(owner, org)
        with pytest.raises(IntegrityError), transaction.atomic():
            Enrollment.objects.create(
                institution_id=org.north.pk, student=ana, year=school["year"],
                unit=school["jamaat"], start_date=dt.date(2027, 1, 1),
            )  # fmt: skip


def test_permissions_follow_the_institution_scope(org, owner, school):
    with tenant_atomic(org.tenant):
        ana = _student(owner, org)
    head = make_user("north-head@example.com", mfa=True).user
    grant_role(org.tenant, head, "institution_admin", institution=org.south)
    with tenant_atomic(org.tenant):
        with pytest.raises(PermissionDenied):
            services.create_student(
                actor=head, institution=org.north, values={"name": "X"}, number="9"
            )
        with pytest.raises(PermissionDenied):
            services.update_student(actor=head, student=ana, values={"name": "Y"})
        with pytest.raises(PermissionDenied):
            services.enroll(actor=org.teacher, student=ana, year=school["year"], unit=school["a"])
        with pytest.raises(PermissionDenied):
            services.link_guardian(
                actor=org.teacher, student=ana, values={"name": "R", "phone": "01711000001"}
            )


def test_students_and_guardians_are_invisible_to_another_tenant(org, owner, tenant_site):
    with tenant_atomic(org.tenant):
        ana = _student(owner, org)
        services.link_guardian(
            actor=owner, student=ana, values={"name": "Rina", "phone": "01711000000"},
            relation="mother",
        )  # fmt: skip
    other = tenant_site(slug="bravo")
    seed_tenant_roles(other)
    with tenant_atomic(other):
        assert not Student.objects.exists() and not Guardian.objects.exists()
        assert services.match_guardian(phone="01711000000") is None  # never across tenants
        with connection.cursor() as cursor:
            for table in ("students_student", "students_guardian", "students_studentguardian"):
                cursor.execute(f"SELECT count(*) FROM {table}")
                assert cursor.fetchone() == (0,)
