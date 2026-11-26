"""Accepted application → student (Phase 7 M4; ADR-065, ADR-074 Q4/Q8; plan §6): the student,
the guardian (matched within the tenant), the enrollment when the admitted unit is a leaf,
idempotency, tenants without the module, a failed conversion and the staff retry."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from apps.academics import services as academics
from apps.admissions import services as admissions
from apps.audit.models import AuditEvent
from apps.core.tenancy import tenant_atomic
from apps.customization import fields, forms, numbering
from apps.module_registry import services as registry_services
from apps.students import services as student_services
from apps.students.conversion import convert
from apps.students.models import Enrollment, Guardian, Student, StudentGuardian
from apps.tenancy.models import Institution
from tests.helpers import Api, make_user
from tests.isolation.factories import grant_role, tenant_host

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])
V1 = "/api/v1"
LAYOUT = {
    "sections": [
        {
            "key": "applicant",
            "labels": {"en": "Applicant"},
            "fields": [
                {"source": "core", "name": name}
                for name in (
                    "applicant_name",
                    "applicant_email",
                    "applicant_phone",
                    "date_of_birth",
                    "guardian_name",
                    "guardian_phone",
                )
            ],
        }
    ]
}


@pytest.fixture
def owner(org):
    user = make_user("conversion-owner@example.com", mfa=True).user
    grant_role(org.tenant, user, "tenant_owner")
    return user


def _grant(admin, org, *modules: str) -> None:
    for module in modules:
        registry_services.set_override(
            actor=admin.user, tenant_id=org.tenant.id, module_code=module, kind="grant",
            reason="Pilot agreement for students",
        )  # fmt: skip


@pytest.fixture
def setup(org, owner):
    """North (school): a 2027 year, class Six (a leaf for now) and an open cycle for it."""
    with tenant_atomic(org.tenant):
        Institution.objects.filter(pk=org.north.pk).update(
            preset_code="school.general.v2", preset_version="2"
        )
        year = academics.create_year(
            actor=owner, institution=org.north, code="2027", name="2027",
            start_date=dt.date(2027, 1, 1), end_date=dt.date(2027, 12, 31),
        )  # fmt: skip
        six = academics.create_unit(
            actor=owner, institution=org.north, level_key="class", code="6", name="Six"
        )
        forms.save_form_draft(
            actor=owner, key="admission", entity="admissions.application", name="A", layout=LAYOUT
        )
        forms.publish_form(actor=owner, key="admission")
        cycle = admissions.create_cycle(
            actor=owner, institution=org.north, year=year, code="c27", name="c27",
            opens_on=dt.date(2026, 11, 1), closes_on=dt.date(2027, 1, 31), form_key="admission",
        )  # fmt: skip
        target = admissions.add_target(actor=owner, cycle=cycle, unit=six, capacity=10)
        admissions.set_cycle_status(actor=owner, cycle=cycle, status="open")
    return {"year": year, "six": six, "cycle": cycle, "target": target}


def _accept(org, owner, setup, capture, **values: Any) -> Any:
    """An application with these values, offered and accepted (hooks run after commit)."""
    with tenant_atomic(org.tenant):
        app = admissions.create_application(
            actor=owner, cycle=setup["cycle"], target=setup["target"],
            values={"applicant_name": "Rahim", **values},
        )  # fmt: skip
        admissions.start_review(actor=owner, application=app)
        admissions.decide(actor=owner, application=app, decision="offered")
    with capture(execute=True), tenant_atomic(org.tenant):
        admissions.record_offer_response(actor=owner, application=app, accept=True)
    return app


def test_acceptance_creates_the_student_the_guardian_and_the_enrollment(
    org, owner, admin, setup, django_capture_on_commit_callbacks
):
    _grant(admin, org, "academics", "students")
    app = _accept(
        org, owner, setup, django_capture_on_commit_callbacks, applicant_email="R@Example.com",
        applicant_phone="01711-000001", date_of_birth="2015-02-01", guardian_name="Karim",
        guardian_phone="01711 000 009",
    )  # fmt: skip
    with tenant_atomic(org.tenant):
        student = Student.objects.get(source_application_id=app.pk)
        assert (student.name, student.email, student.phone, str(student.date_of_birth)) == (
            "Rahim", "r@example.com", "01711000001", "2015-02-01",
        )  # fmt: skip
        assert student.number == f"APP-{app.pk.hex[-12:]}"  # no sequence, no application number
        link = StudentGuardian.objects.get(student=student)
        guardian = Guardian.objects.get(pk=link.guardian_id)
        assert (guardian.name, guardian.phone, link.is_primary) == (
            "Karim", "01711000009", True,
        )  # fmt: skip
        enrollment = Enrollment.objects.get(student=student)  # Six has no sections: enrolled
        assert (enrollment.unit_id, enrollment.status) == (setup["six"].pk, "active")
        assert convert(app.pk) == student  # idempotent
        assert Student.objects.filter(source_application_id=app.pk).count() == 1
    # A sibling with the same guardian phone links the same guardian (matched in the tenant).
    with tenant_atomic(org.tenant):
        numbering.define_sequence(
            actor=owner, key="student", name="Students", pattern="STU-{SEQ:3}",
            scope="institution", reset="never",
        )  # fmt: skip
    sibling = _accept(org, owner, setup, django_capture_on_commit_callbacks,
                      applicant_name="Sara", guardian_phone="01711-000-009")  # fmt: skip
    with tenant_atomic(org.tenant):
        sara = Student.objects.get(source_application_id=sibling.pk)
        assert sara.number == "STU-001"  # the Studio sequence, once defined
        assert Guardian.objects.count() == 1
        link = StudentGuardian.objects.get(student=sara)
        assert Guardian.objects.get(pk=link.guardian_id).name == "Karim"
        assert AuditEvent.objects.filter(action="students.student.converted").count() == 2


def test_custom_values_matching_student_fields_are_copied(org, owner, admin, setup):
    _grant(admin, org, "academics", "students")
    with tenant_atomic(org.tenant):
        fields.define_field(
            actor=owner, entity="students.student", key="blood_group", field_type="text",
            labels={"en": "Blood group"},
        )  # fmt: skip
        app = admissions.create_application(
            actor=owner, cycle=setup["cycle"], target=setup["target"],
            values={"applicant_name": "Nila"},
        )  # fmt: skip
        type(app).objects.filter(pk=app.pk).update(
            status="accepted", extra={"blood_group": "O+", "shoe_size": 40}
        )
        student = convert(app.pk)
        assert student is not None and student.extra == {"blood_group": "O+"}


def test_a_class_with_sections_waits_for_staff_to_choose(
    org, owner, admin, setup, django_capture_on_commit_callbacks
):
    _grant(admin, org, "academics", "students")
    with tenant_atomic(org.tenant):
        academics.create_unit(
            actor=owner, institution=org.north, level_key="section", code="6A", name="A",
            parent=setup["six"],
        )  # fmt: skip
    app = _accept(org, owner, setup, django_capture_on_commit_callbacks, guardian_name="Karim")
    with tenant_atomic(org.tenant):
        student = Student.objects.get(source_application_id=app.pk)
        assert not Enrollment.objects.filter(student=student).exists()
        assert not StudentGuardian.objects.filter(student=student).exists()  # no phone


def test_tenants_without_the_students_module_are_left_alone(
    org, owner, setup, django_capture_on_commit_callbacks
):
    app = _accept(org, owner, setup, django_capture_on_commit_callbacks)
    with tenant_atomic(org.tenant):
        assert type(app).objects.get(pk=app.pk).status == "accepted"
        assert not Student.objects.exists()


def test_a_failed_conversion_is_audited_and_staff_retry_it(
    org, owner, admin, setup, settings, django_capture_on_commit_callbacks
):
    _grant(admin, org, "academics", "students")
    settings.STUDIO_QUOTA_DEFAULTS = {**settings.STUDIO_QUOTA_DEFAULTS, "max_active_students": 1}
    with tenant_atomic(org.tenant):
        student_services.create_student(
            actor=owner, institution=org.north, values={"name": "Old"}, number="1"
        )
    app = _accept(org, owner, setup, django_capture_on_commit_callbacks)
    with tenant_atomic(org.tenant):
        assert not Student.objects.filter(source_application_id=app.pk).exists()
        failed = AuditEvent.objects.get(action="students.student.conversion_failed")
        assert failed.metadata == {"reason": "quota"}
    api_body = {"application": str(app.pk)}
    head = make_user("conv-head@example.com", mfa=True)
    grant_role(org.tenant, head.user, "institution_admin", institution=org.north)
    api = Api(host=tenant_host(org.tenant))
    api.login(head, expect="authenticated")
    api.step_up(head)
    assert api.post(f"{V1}/students/from-application/", api_body).status_code == 400  # still full
    settings.STUDIO_QUOTA_DEFAULTS = {**settings.STUDIO_QUOTA_DEFAULTS, "max_active_students": 0}
    created = api.post(f"{V1}/students/from-application/", api_body)
    assert created.status_code == 201, created.content
    assert created.json()["enrollments"][0]["unit_name"] == "Six"
    again = api.post(f"{V1}/students/from-application/", api_body)
    assert (again.status_code, again.json()["id"]) == (200, created.json()["id"])
    south = make_user("conv-south@example.com", mfa=True)
    grant_role(org.tenant, south.user, "institution_admin", institution=org.south)
    other = Api(host=tenant_host(org.tenant))
    other.login(south, expect="authenticated")
    other.step_up(south)
    assert other.post(f"{V1}/students/from-application/", api_body).status_code == 404
    unknown = {"application": "00000000-0000-7000-8000-000000000000"}
    assert api.post(f"{V1}/students/from-application/", unknown).status_code == 404
