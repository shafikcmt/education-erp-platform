"""Admissions back office (Phase 6 M4; ADR-065): inquiries, cycles bound to Studio artefacts,
applications validated by the cycle's form, the built-in review path and a workflow review,
decisions within capacity, offer answers with the acceptance hook, scopes, isolation and API."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection

from apps.academics import services as academics
from apps.admissions import services
from apps.admissions.models import Application, Inquiry
from apps.core.tenancy import tenant_atomic
from apps.customization import forms, numbering, workflows
from apps.customization.models import WorkflowInstance
from apps.module_registry import services as registry_services
from apps.tenancy.models import Institution, Membership
from tests.helpers import Api, make_user
from tests.isolation.factories import grant_role, seed_tenant_roles, tenant_host

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])

LAYOUT = {
    "sections": [
        {
            "key": "applicant",
            "labels": {"en": "Applicant"},
            "fields": [
                {"source": "core", "name": "applicant_name", "required": True},
                {"source": "core", "name": "applicant_email"},
                {"source": "core", "name": "date_of_birth"},
                {"source": "core", "name": "guardian_name"},
            ],
        }
    ]
}
REVIEW_FLOW = {
    "states": [
        {"key": "screening", "labels": {"en": "Screening"}},
        {"key": "done", "labels": {"en": "Done"}, "final": True},
    ],
    "initial": "screening",
    "start_permission": "admissions.application.review",
    "transitions": [
        {"key": "complete", "from": ["screening"], "to": "done", "labels": {"en": "Complete"},
         "permission": "admissions.application.review"},
    ],
}  # fmt: skip


@pytest.fixture
def owner(org):
    user = make_user("admissions-owner@example.com", mfa=True).user
    grant_role(org.tenant, user, "tenant_owner")
    return user


@pytest.fixture
def setup(org, owner):
    """North (a school) with a 2027 year, class 6, a published application form, a workflow
    and a numbering sequence."""
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
        workflows.save_workflow_draft(
            actor=owner, key="screening", subject="admissions.application", name="S",
            spec=REVIEW_FLOW,
        )  # fmt: skip
        workflows.publish_workflow(actor=owner, key="screening")
        numbering.define_sequence(
            actor=owner, key="application", name="Apps", pattern="APP-{YYYY}-{SEQ:4}",
            reset="yearly",
        )  # fmt: skip
    return year, six


def _cycle(owner, org, year, six, code="c27", capacity=1, **kw):
    cycle = services.create_cycle(
        actor=owner, institution=org.north, year=year, code=code, name=code,
        opens_on=dt.date(2026, 11, 1), closes_on=dt.date(2027, 1, 31), form_key="admission", **kw,
    )  # fmt: skip
    target = services.add_target(actor=owner, cycle=cycle, unit=six, capacity=capacity)
    services.set_cycle_status(actor=owner, cycle=cycle, status="open")
    return cycle, target


def test_inquiries_need_a_contact_and_follow_up(org, owner):
    with tenant_atomic(org.tenant):
        with pytest.raises(ValidationError):
            services.create_inquiry(actor=owner, institution=org.north, values={"name": "A"})
        inquiry = services.create_inquiry(
            actor=owner, institution=org.north,
            values={"name": "A", "phone": "01700000000", "source": "walk_in"},
        )  # fmt: skip
        assignee = Membership.objects.get(user=org.head)
        services.update_inquiry(
            actor=owner, inquiry=inquiry,
            changes={"status": "contacted", "assigned_to": assignee.pk},
        )  # fmt: skip
        assert Inquiry.objects.get(pk=inquiry.pk).assigned_to_id == assignee.pk


def test_cycles_only_bind_published_admissions_artefacts(org, owner, setup):
    year, _ = setup
    with tenant_atomic(org.tenant):
        for bad in ({"form_key": "nope"}, {"workflow_key": "nope"}, {"numbering_key": "nope"},
                    {"merit_rule_key": "nope"}, {"fee_amount": 100}):  # fmt: skip
            kwargs: dict[str, Any] = {"form_key": "admission", **bad}
            with pytest.raises(ValidationError):
                services.create_cycle(
                    actor=owner, institution=org.north, year=year, code="x", name="x",
                    opens_on=dt.date(2026, 11, 1), closes_on=dt.date(2027, 1, 31), **kwargs,
                )  # fmt: skip
        draft = services.create_cycle(
            actor=owner, institution=org.north, year=year, code="d", name="d",
            opens_on=dt.date(2026, 11, 1), closes_on=dt.date(2027, 1, 31), form_key="admission",
        )  # fmt: skip
        with pytest.raises(ValidationError, match="target"):
            services.set_cycle_status(actor=owner, cycle=draft, status="open")


def test_built_in_review_decisions_within_capacity_and_the_acceptance_hook(
    org, owner, setup, settings, django_capture_on_commit_callbacks
):
    settings.ADMISSIONS_ACCEPTED_HANDLERS = ["apps.admissions.tests.test_admissions.record_call"]
    RECORDED.clear()
    year, six = setup
    with tenant_atomic(org.tenant):
        cycle, target = _cycle(owner, org, year, six, numbering_key="application")
        values = {"applicant_name": "Rahim", "applicant_email": "r@example.com",
                  "date_of_birth": "2015-02-01", "guardian_name": "Karim"}  # fmt: skip
        first = services.create_application(actor=owner, cycle=cycle, target=target, values=values)
        assert first.number == f"APP-{dt.date.today().year}-0001" and first.status == "submitted"
        assert first.core == {"guardian_name": "Karim"} and str(first.date_of_birth) == "2015-02-01"
        second = services.create_application(
            actor=owner, cycle=cycle, target=target, values={"applicant_name": "Sara"}
        )
        with pytest.raises(ValidationError):  # form validation on the server
            services.create_application(actor=owner, cycle=cycle, target=target, values={})
        with pytest.raises(ValidationError):
            services.create_application(
                actor=owner, cycle=cycle, target=target,
                values={"applicant_name": "X", "applicant_email": "not-an-email"},
            )  # fmt: skip
        services.start_review(actor=owner, application=first)
        services.decide(actor=owner, application=first, decision="offered")
        with pytest.raises(ValidationError, match="No seat"):  # capacity 1
            services.decide(actor=owner, application=second, decision="offered")
        services.decide(actor=owner, application=second, decision="rejected", note="Full")
    with django_capture_on_commit_callbacks(execute=True), tenant_atomic(org.tenant):
        services.record_offer_response(actor=owner, application=first, accept=True)
    assert [(str(org.tenant.id), str(first.pk))] == RECORDED
    with tenant_atomic(org.tenant):
        assert Application.objects.get(pk=first.pk).status == "accepted"
        with pytest.raises(ValidationError):
            services.record_offer_response(actor=owner, application=first, accept=False)


RECORDED: list[tuple[str, str]] = []


def record_call(*, tenant_id: str, application_id: str) -> None:
    RECORDED.append((tenant_id, application_id))


def test_a_workflow_review_must_finish_before_the_decision(org, owner, setup):
    year, six = setup
    with tenant_atomic(org.tenant):
        cycle, target = _cycle(owner, org, year, six, workflow_key="screening")
        app = services.create_application(
            actor=owner, cycle=cycle, target=target, values={"applicant_name": "Rahim"}
        )
        assert app.workflow_instance_id is not None
        with pytest.raises(ValidationError, match="workflow"):
            services.start_review(actor=owner, application=app)
        with pytest.raises(ValidationError, match="Finish"):
            services.decide(actor=owner, application=app, decision="offered")
        workflows.transition(
            actor=owner, instance_id=app.workflow_instance_id, transition_key="complete"
        )
        assert WorkflowInstance.objects.get(pk=app.workflow_instance_id).finished_at
        assert services.decide(actor=owner, application=app, decision="offered").status == "offered"


def test_permissions_follow_the_institution_scope(org, owner, setup):
    year, six = setup
    officer = make_user("officer@example.com", mfa=True).user
    grant_role(org.tenant, officer, "admission_officer", institution=org.north)
    with tenant_atomic(org.tenant):
        cycle, target = _cycle(owner, org, year, six)
        app = services.create_application(
            actor=officer, cycle=cycle, target=target, values={"applicant_name": "Rahim"}
        )
        services.start_review(actor=officer, application=app)
        with pytest.raises(PermissionDenied):  # officers review; heads decide
            services.decide(actor=officer, application=app, decision="offered")
        with pytest.raises(PermissionDenied):
            services.create_inquiry(
                actor=officer, institution=org.south, values={"name": "A", "phone": "1"}
            )


def test_applications_are_invisible_to_another_tenant(org, owner, setup, tenant_site):
    year, six = setup
    with tenant_atomic(org.tenant):
        cycle, target = _cycle(owner, org, year, six)
        app = services.create_application(
            actor=owner, cycle=cycle, target=target, values={"applicant_name": "Rahim"}
        )
    other = tenant_site(slug="bravo")
    seed_tenant_roles(other)
    with tenant_atomic(other):
        assert not Application.objects.exists()
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM admissions_application WHERE id = %s", [app.pk])
            assert cursor.fetchone() == (0,)


def test_api_back_office_and_scopes(org, owner, setup, admin):
    for module in ("academics", "admissions"):  # admissions depends on academics
        registry_services.set_override(
            actor=admin.user, tenant_id=org.tenant.id, module_code=module, kind="grant",
            reason="Pilot agreement for admissions",
        )  # fmt: skip
    year, six = setup
    with tenant_atomic(org.tenant):
        cycle, target = _cycle(owner, org, year, six)
    person = make_user("api-officer@example.com", mfa=True)
    grant_role(org.tenant, person.user, "admission_officer", institution=org.north)
    api = Api(host=tenant_host(org.tenant))
    api.login(person, expect="authenticated")
    api.step_up(person)
    north, south = str(org.north.pk), str(org.south.pk)
    assert api.get("/api/v1/admissions/cycles/", institution=north).json()[0]["code"] == "c27"
    assert api.get("/api/v1/admissions/cycles/", institution=south).status_code == 404
    created = api.post(
        "/api/v1/admissions/applications/",
        {"cycle": str(cycle.pk), "target": str(target.pk), "values": {"applicant_name": "Ana"}},
    )
    assert created.status_code == 201, created.content
    listed = api.get("/api/v1/admissions/applications/", cycle=str(cycle.pk)).json()
    assert [a["applicant_name"] for a in listed] == ["Ana"]
    app_id = created.json()["id"]
    assert api.post(f"/api/v1/admissions/applications/{app_id}/review/").status_code == 200
    denied = api.post(
        f"/api/v1/admissions/applications/{app_id}/decision/", {"decision": "offered"}
    )
    assert denied.status_code == 403
    inquiry = api.post(
        "/api/v1/admissions/inquiries/", {"institution": north, "name": "B", "email": "b@x.org"}
    )
    assert inquiry.status_code == 201, inquiry.content
