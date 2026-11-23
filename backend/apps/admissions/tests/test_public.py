"""Public admissions on tenant hosts (Phase 6 M5; ADR-065): open cycles, the form, apply →
email verification → status link, offer answers, documents, abuse controls, housekeeping
(P26), the workflow start at review, the module gate and isolation."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from django.core import mail
from django.utils import timezone

from apps.academics import services as academics
from apps.admissions import public, services
from apps.admissions.models import Application, Cycle
from apps.admissions.tasks import purge
from apps.audit.models import AuditEvent
from apps.core.tenancy import tenant_atomic
from apps.customization import forms, numbering, workflows
from apps.files.models import StoredFile
from apps.module_registry import services as registry_services
from apps.tenancy.models import Institution
from tests.helpers import Api, link_token, make_user
from tests.isolation.factories import grant_role, tenant_host

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])
P = "/api/v1/public/admissions"
LAYOUT = {
    "sections": [
        {
            "key": "applicant",
            "labels": {"en": "Applicant"},
            "fields": [
                {"source": "core", "name": "applicant_name", "required": True},
                {"source": "core", "name": "applicant_email", "required": True},
                {"source": "core", "name": "date_of_birth"},
            ],
        }
    ]
}
FLOW = {
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
    user = make_user("public-owner@example.com", mfa=True).user
    grant_role(org.tenant, user, "tenant_owner")
    return user


@pytest.fixture
def entitled(org, admin):
    for module in ("academics", "admissions"):
        registry_services.set_override(
            actor=admin.user, tenant_id=org.tenant.id, module_code=module, kind="grant",
            reason="Pilot agreement for admissions",
        )  # fmt: skip


@pytest.fixture
def cycle(org, owner):
    """An open cycle (dates relative to today) with a form, a workflow and numbering."""
    today = dt.date.today()
    with tenant_atomic(org.tenant):
        Institution.objects.filter(pk=org.north.pk).update(
            preset_code="school.general.v2", preset_version="2"
        )
        year = academics.create_year(
            actor=owner, institution=org.north, code="next", name="Next",
            start_date=today + dt.timedelta(days=60), end_date=today + dt.timedelta(days=420),
        )  # fmt: skip
        six = academics.create_unit(
            actor=owner, institution=org.north, level_key="class", code="6", name="Six"
        )
        forms.save_form_draft(
            actor=owner, key="admission", entity="admissions.application", name="A", layout=LAYOUT
        )
        forms.publish_form(actor=owner, key="admission")
        workflows.save_workflow_draft(
            actor=owner, key="screening", subject="admissions.application", name="S", spec=FLOW
        )
        workflows.publish_workflow(actor=owner, key="screening")
        numbering.define_sequence(
            actor=owner, key="application", name="Apps", pattern="APP-{SEQ:4}", reset="never"
        )
        row = services.create_cycle(
            actor=owner, institution=org.north, year=year, code="c", name="Class six",
            opens_on=today - dt.timedelta(days=1), closes_on=today + dt.timedelta(days=30),
            form_key="admission", workflow_key="screening", numbering_key="application",
        )  # fmt: skip
        target = services.add_target(actor=owner, cycle=row, unit=six, capacity=2)
        services.set_cycle_status(actor=owner, cycle=row, status="open")
    return row, target


def _body(target, email="ana@example.com", **extra: Any) -> dict[str, Any]:
    values = {"applicant_name": "Ana", "applicant_email": email}
    return {"target": str(target.pk), "values": values, **extra}


def _apply(api, row, target, callbacks, **kw) -> Any:
    with callbacks(execute=True):
        return api.post(f"{P}/cycles/{row.pk}/apply/", _body(target, **kw))


def _through_verify(org, cycle, callbacks) -> tuple[Api, str]:
    row, target = cycle
    anon = Api(host=tenant_host(org.tenant))
    assert _apply(anon, row, target, callbacks).status_code == 202
    token = link_token(mail.outbox[-1], "apply/verify")
    with callbacks(execute=True):
        assert anon.post(f"{P}/verify/", {"token": token}).status_code == 200
    return anon, link_token(mail.outbox[-1], "apply/status")


def test_without_the_module_every_public_route_is_not_found(org, cycle):
    anon = Api(host=tenant_host(org.tenant))
    row, _ = cycle
    assert anon.get(f"{P}/cycles/").status_code == 404
    assert anon.post(f"{P}/cycles/{row.pk}/apply/", {}).status_code == 404
    assert anon.post(f"{P}/status/", {"token": "x"}).status_code == 404


def test_open_cycles_and_the_form(org, entitled, cycle):
    row, target = cycle
    anon = Api(host=tenant_host(org.tenant))
    [listed] = anon.get(f"{P}/cycles/").json()
    assert listed["id"] == str(row.pk) and listed["targets"][0]["id"] == str(target.pk)
    assert anon.get(f"{P}/cycles/{row.pk}/form/").status_code == 200
    with tenant_atomic(org.tenant):
        Cycle.objects.filter(pk=row.pk).update(status=Cycle.Status.CLOSED)
    assert anon.get(f"{P}/cycles/").json() == []
    assert anon.get(f"{P}/cycles/{row.pk}/form/").status_code == 400


def test_apply_verify_status_and_the_offer(
    org, owner, entitled, cycle, django_capture_on_commit_callbacks
):
    callbacks = django_capture_on_commit_callbacks
    row, target = cycle
    anon = Api(host=tenant_host(org.tenant))
    response = _apply(anon, row, target, callbacks)
    assert response.status_code == 202, response.content
    with tenant_atomic(org.tenant):
        draft = Application.objects.get()
    assert (draft.status, draft.source, draft.number) == ("draft", "public", "")
    [message] = mail.outbox
    token = link_token(message, "apply/verify")
    assert message.to == ["ana@example.com"] and draft.verify_token_hash != token
    with tenant_atomic(org.tenant):  # tenant audit events are under RLS
        event = AuditEvent.objects.get(action="admissions.application.drafted")
    assert "ana@" not in str(event.metadata)

    with callbacks(execute=True):
        assert anon.post(f"{P}/verify/", {"token": token}).status_code == 200
    assert anon.post(f"{P}/verify/", {"token": token}).status_code == 400  # single use
    status_token = link_token(mail.outbox[-1], "apply/status")
    status = anon.post(f"{P}/status/", {"token": status_token}).json()
    assert status["status"] == "submitted" and status["number"] == "APP-0001"
    assert status["can_add_documents"] is True
    assert anon.post(f"{P}/status/", {"token": "wrong"}).status_code == 400
    early = anon.post(f"{P}/status/respond/", {"token": status_token, "accept": True})
    assert early.status_code == 400  # nothing offered yet

    with tenant_atomic(org.tenant):
        app = Application.objects.get()
        assert app.workflow_instance_id is None  # no member could start it at submission
        app = services.start_review(actor=owner, application=app)
        assert app.workflow_instance_id is not None  # started when staff take it in
        workflows.transition(
            actor=owner, instance_id=app.workflow_instance_id, transition_key="complete"
        )
        services.decide(actor=owner, application=app, decision="offered", note="Welcome")
    status = anon.post(f"{P}/status/", {"token": status_token}).json()
    assert (status["status"], status["decision_note"]) == ("offered", "Welcome")
    answered = anon.post(f"{P}/status/respond/", {"token": status_token, "accept": True})
    assert answered.status_code == 200, answered.content
    assert answered.json()["status"] == "accepted"


def test_abuse_controls(org, entitled, cycle, settings, django_capture_on_commit_callbacks):
    callbacks = django_capture_on_commit_callbacks
    row, target = cycle
    anon = Api(host=tenant_host(org.tenant))
    bot = _apply(anon, row, target, callbacks, website="https://spam.example")
    assert bot.status_code == 202 and not mail.outbox  # honeypot: silent no-op
    with tenant_atomic(org.tenant):
        assert not Application.objects.exists()
    answers = [
        _apply(
            Api(host=tenant_host(org.tenant), remote_addr=f"203.0.113.{i}"), row, target, callbacks
        )
        for i in range(5)
    ]
    assert {(a.status_code, a.json()["detail"]) for a in answers} == {(202, bot.json()["detail"])}
    assert len(mail.outbox) == 3  # per-email limit is silent
    burst = Api(host=tenant_host(org.tenant), remote_addr="198.51.100.99")
    codes = [
        _apply(burst, row, target, callbacks, email=f"p{i}@example.com").status_code
        for i in range(11)
    ]
    assert codes[:10] == [202] * 10 and codes[10] == 429


def test_expired_drafts_are_purged_and_past_cycles_close(
    org, entitled, cycle, django_capture_on_commit_callbacks
):
    row, target = cycle
    anon = Api(host=tenant_host(org.tenant))
    _apply(anon, row, target, django_capture_on_commit_callbacks)
    token = link_token(mail.outbox[-1], "apply/verify")
    with tenant_atomic(org.tenant):
        Application.objects.update(verify_expires_at=timezone.now() - dt.timedelta(minutes=1))
    assert anon.post(f"{P}/verify/", {"token": token}).status_code == 400  # expired
    result = purge.apply(kwargs={"tenant_id": str(org.tenant.id)}).get()  # P26, per tenant
    assert result == {"drafts": 1, "cycles": 0}
    with tenant_atomic(org.tenant):
        assert not Application.objects.exists()
        assert public.close_past_cycles(dt.date.today() + dt.timedelta(days=31)) == 1
        assert Cycle.objects.get(pk=row.pk).status == "closed"


def test_documents_with_the_status_link_and_for_staff(
    org, owner, entitled, cycle, django_capture_on_commit_callbacks
):
    anon, token = _through_verify(org, cycle, django_capture_on_commit_callbacks)
    bad = anon.post(
        f"{P}/status/documents/",
        {"token": token, "name": "a.exe", "size": 10, "content_type": "application/x-msdownload"},
    )
    assert bad.status_code == 400
    slot = anon.post(
        f"{P}/status/documents/",
        {"token": token, "name": "birth.pdf", "size": 1000, "content_type": "application/pdf"},
    )
    assert slot.status_code == 201, slot.content
    file_id = slot.json()["id"]
    with django_capture_on_commit_callbacks(execute=False):
        confirmed = anon.post(f"{P}/status/documents/confirm/", {"token": token, "file": file_id})
    assert confirmed.status_code == 200, confirmed.content
    assert [d["name"] for d in confirmed.json()["documents"]] == ["birth.pdf"]
    again = anon.post(f"{P}/status/documents/confirm/", {"token": token, "file": file_id})
    assert again.status_code == 400

    with tenant_atomic(org.tenant):
        app = Application.objects.get()
        StoredFile.objects.filter(pk=file_id).update(status=StoredFile.Status.READY)
    staff = Api(host=tenant_host(org.tenant))
    person = make_user("doc-officer@example.com", mfa=True)
    grant_role(org.tenant, person.user, "admission_officer", institution=org.north)
    staff.login(person, expect="authenticated")
    base = f"/api/v1/admissions/applications/{app.pk}/documents/"
    assert [d["id"] for d in staff.get(base).json()] == [file_id]
    link = staff.get(f"{base}{file_id}/download/")
    assert link.status_code == 200, link.content and link.json()["url"]
    assert staff.get(f"{base}00000000-0000-0000-0000-000000000000/download/").status_code == 404
    outsider = make_user("south-officer@example.com", mfa=True)
    grant_role(org.tenant, outsider.user, "admission_officer", institution=org.south)
    other = Api(host=tenant_host(org.tenant))
    other.login(outsider, expect="authenticated")
    assert other.get(base).status_code == 404


def test_status_tokens_do_not_cross_tenants(
    org, entitled, cycle, admin, tenant_site, django_capture_on_commit_callbacks
):
    _, token = _through_verify(org, cycle, django_capture_on_commit_callbacks)
    other = tenant_site(slug="bravo")
    for module in ("academics", "admissions"):
        registry_services.set_override(
            actor=admin.user, tenant_id=other.id, module_code=module, kind="grant",
            reason="Pilot agreement for admissions",
        )  # fmt: skip
    elsewhere = Api(host=tenant_host(other))
    assert elsewhere.post(f"{P}/status/", {"token": token}).status_code == 400
    assert elsewhere.get(f"{P}/cycles/").json() == []
