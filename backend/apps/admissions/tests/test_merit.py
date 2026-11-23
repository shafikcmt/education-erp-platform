"""Admission tests, scores, the merit list and offers by merit (Phase 6 M6; ADR-065)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.utils import timezone

from apps.academics import services as academics
from apps.admissions import merit, services
from apps.admissions.models import Application, MeritList, Test, TestAssignment
from apps.core.tenancy import tenant_atomic
from apps.customization import forms, rule_services, workflows
from apps.module_registry import services as registry_services
from apps.tenancy.models import Institution
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
                {"source": "core", "name": "guardian_name"},
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
# Total score plus 50 for a named guardian (a stand-in for a quota or a bonus).
BONUS = {
    "+": [
        {"var": "application.score"},
        {"if": [{"==": [{"var": "application.guardian_name"}, "Rina"]}, 50, 0]},
    ]
}


@pytest.fixture
def owner(org):
    user = make_user("merit-owner@example.com", mfa=True).user
    grant_role(org.tenant, user, "tenant_owner")
    return user


@pytest.fixture
def world(org, owner):
    """North: a year, class six, an application form, a workflow and the bonus merit rule."""
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
            actor=owner, key="screening", subject="admissions.application", name="S", spec=FLOW
        )
        workflows.publish_workflow(actor=owner, key="screening")
        rule_services.save_rule_draft(
            actor=owner, namespace_code="admissions.merit", key="bonus", name="Bonus", rule=BONUS,
            test_cases=[{"context": {"application.score": 10, "application.guardian_name": "Rina"},
                         "expected": 60}],
        )  # fmt: skip
        rule_services.publish_rule(actor=owner, key="bonus")
    return year, six


def _cycle(owner, org, world, *, capacity=2, code="c", **kw: Any):
    year, six = world
    cycle = services.create_cycle(
        actor=owner, institution=org.north, year=year, code=code, name=code,
        opens_on=dt.date(2026, 11, 1), closes_on=dt.date(2027, 1, 31), form_key="admission", **kw,
    )  # fmt: skip
    target = services.add_target(actor=owner, cycle=cycle, unit=six, capacity=capacity)
    services.set_cycle_status(actor=owner, cycle=cycle, status="open")
    return cycle, target


def _apply(owner, cycle, target, name: str, guardian: str = "") -> Application:
    values = {"applicant_name": name, **({"guardian_name": guardian} if guardian else {})}
    app = services.create_application(actor=owner, cycle=cycle, target=target, values=values)
    if app.workflow_instance_id is None:
        app = services.start_review(actor=owner, application=app)
    return app


def _test(owner, cycle, *, capacity=10, max_score="100"):
    return merit.create_test(
        actor=owner, cycle=cycle, name="Written", starts_at=timezone.now(), capacity=capacity,
        max_score=Decimal(max_score), venue="Hall A",
    )  # fmt: skip


def _scored(owner, cycle, test, target, name: str, score: str, guardian: str = ""):
    app = _apply(owner, cycle, target, name, guardian)
    seat = merit.assign_test(actor=owner, test=test, application=app)
    merit.record_score(actor=owner, assignment=seat, score=Decimal(score))
    return Application.objects.get(pk=app.pk)


def test_tests_seat_score_and_evaluate(org, owner, world):
    with tenant_atomic(org.tenant):
        cycle, target = _cycle(owner, org, world)
        other, other_target = _cycle(owner, org, world, code="other")
        test = _test(owner, cycle, capacity=2)
        second = merit.create_test(
            actor=owner, cycle=cycle, name="Viva", starts_at=timezone.now(), capacity=5,
            max_score=Decimal("20"),
        )  # fmt: skip
        ana = _apply(owner, cycle, target, "Ana")
        seat = merit.assign_test(actor=owner, test=test, application=ana)
        assert seat.seat == 1 and Application.objects.get(pk=ana.pk).status == "test_scheduled"
        with pytest.raises(ValidationError, match="already seated"):
            merit.assign_test(actor=owner, test=test, application=ana)
        stranger = _apply(owner, other, other_target, "Out")
        with pytest.raises(ValidationError, match="this test's cycle"):
            merit.assign_test(actor=owner, test=test, application=stranger)
        merit.assign_test(actor=owner, test=test, application=_apply(owner, cycle, target, "Bo"))
        with pytest.raises(ValidationError, match="full"):
            merit.assign_test(actor=owner, test=test, application=_apply(owner, cycle, target, "C"))
        viva = merit.assign_test(actor=owner, test=second, application=ana)
        with pytest.raises(ValidationError, match="between 0 and 100"):
            merit.record_score(actor=owner, assignment=seat, score=Decimal("101"))
        with pytest.raises(ValidationError, match="absent"):
            merit.record_score(actor=owner, assignment=seat, score=Decimal(1), absent=True)
        merit.record_score(actor=owner, assignment=seat, score=Decimal("71.5"))
        assert Application.objects.get(pk=ana.pk).status == "test_scheduled"  # viva pending
        merit.record_score(actor=owner, assignment=viva, score=None, absent=True)
        ana = Application.objects.get(pk=ana.pk)
        assert (ana.status, ana.score) == ("evaluated", Decimal("71.50"))  # absent scores 0
        merit.record_score(actor=owner, assignment=viva, score=None)  # correction re-opens
        assert Application.objects.get(pk=ana.pk).status == "test_scheduled"
        # Cycles without tests: evaluated directly; with tests, scores decide.
        plain = _apply(owner, cycle, target, "Dee")
        assert merit.mark_evaluated(actor=owner, application=plain).status == "evaluated"
        with pytest.raises(ValidationError, match="in review"):
            merit.mark_evaluated(actor=owner, application=Application.objects.get(pk=ana.pk))


def test_merit_by_score_publish_offers_and_decline_moves_the_list(
    org, owner, world, django_capture_on_commit_callbacks
):
    with tenant_atomic(org.tenant):
        cycle, target = _cycle(owner, org, world, capacity=2)
        test = _test(owner, cycle)
        low = _scored(owner, cycle, test, target, "Low", "40")
        top = _scored(owner, cycle, test, target, "Top", "90")
        mid = _scored(owner, cycle, test, target, "Mid", "65")
        tie = _scored(owner, cycle, test, target, "Tie", "65")  # later submission ranks lower
        order = [r["applicant_name"] for r in merit.ranking(target)]
        assert order == ["Top", "Mid", "Tie", "Low"]
        with pytest.raises(ValidationError, match="Publish a merit list"):
            merit.offer_by_merit(actor=owner, target=target)
        first = merit.publish(actor=owner, target=target)
        assert first.version == 1 and "applicant_name" not in first.ranking[0]  # no names frozen
        assert Application.objects.get(pk=top.pk).merit_rank == 1
        offered = merit.offer_by_merit(actor=owner, target=target)
        assert [a.pk for a in offered] == [top.pk, mid.pk]
        assert merit.offer_by_merit(actor=owner, target=target) == []  # no seat left
        services.record_offer_response(
            actor=owner, application=Application.objects.get(pk=mid.pk), accept=False
        )
        statuses = dict(Application.objects.values_list("pk", "status"))
        assert statuses[mid.pk] == "declined" and statuses[tie.pk] == "offered"  # moved up
        assert statuses[low.pk] == "evaluated"
        assert merit.publish(actor=owner, target=target).version == 2
        assert MeritList.objects.filter(target=target).count() == 2


def test_the_merit_rule_ranks_and_a_failing_rule_stops_publication(org, owner, world):
    with tenant_atomic(org.tenant):
        cycle, target = _cycle(owner, org, world, merit_rule_key="bonus")
        test = _test(owner, cycle)
        _scored(owner, cycle, test, target, "High", "80", guardian="Karim")
        _scored(owner, cycle, test, target, "Bonus", "40", guardian="Rina")
        ranked = merit.ranking(target)
        assert [(r["applicant_name"], r["score"]) for r in ranked] == [
            ("Bonus", "90.00"), ("High", "80.00"),
        ]  # fmt: skip
        _scored(owner, cycle, test, target, "NoGuardian", "99")  # the rule can't read it
        with pytest.raises(ValidationError, match="No value"):
            merit.publish(actor=owner, target=target)
        assert not MeritList.objects.exists()


def test_unfinished_workflow_reviews_are_not_ranked(org, owner, world):
    with tenant_atomic(org.tenant):
        cycle, target = _cycle(owner, org, world, workflow_key="screening")
        test = _test(owner, cycle)
        app = _scored(owner, cycle, test, target, "Ana", "50")
        assert app.status == "evaluated" and merit.ranking(target) == []
        workflows.transition(
            actor=owner, instance_id=app.workflow_instance_id, transition_key="complete"
        )
        assert [r["applicant_name"] for r in merit.ranking(target)] == ["Ana"]


def test_roles_exam_controller_scores_but_cannot_publish(org, owner, world):
    controller = make_user("controller@example.com", mfa=True).user
    grant_role(org.tenant, controller, "exam_controller", institution=org.north)
    with tenant_atomic(org.tenant):
        cycle, target = _cycle(owner, org, world)
        test = _test(owner, cycle)
        app = _apply(owner, cycle, target, "Ana")
        seat = merit.assign_test(actor=controller, test=test, application=app)
        merit.record_score(actor=controller, assignment=seat, score=Decimal(50))
        with pytest.raises(PermissionDenied):
            merit.publish(actor=controller, target=target)
        with pytest.raises(PermissionDenied):
            merit.offer_by_merit(actor=controller, target=target)


def test_tests_and_merit_lists_are_invisible_to_another_tenant(org, owner, world, tenant_site):
    with tenant_atomic(org.tenant):
        cycle, target = _cycle(owner, org, world)
        test = _test(owner, cycle)
        _scored(owner, cycle, test, target, "Ana", "50")
        merit.publish(actor=owner, target=target)
    other = tenant_site(slug="bravo")
    seed_tenant_roles(other)
    with tenant_atomic(other):
        assert not Test.objects.exists() and not TestAssignment.objects.exists()
        assert not MeritList.objects.exists()
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM admissions_test WHERE id = %s", [test.pk])
            assert cursor.fetchone() == (0,)


def test_api_tests_scores_merit_and_step_up(org, owner, world, admin):
    for module in ("academics", "admissions"):
        registry_services.set_override(
            actor=admin.user, tenant_id=org.tenant.id, module_code=module, kind="grant",
            reason="Pilot agreement for admissions",
        )  # fmt: skip
    with tenant_atomic(org.tenant):
        cycle, target = _cycle(owner, org, world)
        app = _apply(owner, cycle, target, "Ana")
    head = make_user("api-head@example.com", mfa=True)
    grant_role(org.tenant, head.user, "institution_admin", institution=org.north)
    api = Api(host=tenant_host(org.tenant))
    api.login(head, expect="authenticated")
    created = api.post(
        f"/api/v1/admissions/cycles/{cycle.pk}/tests/",
        {"name": "Written", "starts_at": timezone.now().isoformat(), "capacity": 5,
         "max_score": "100"},
    )  # fmt: skip
    assert created.status_code == 201, created.content
    test_id = created.json()["id"]
    seated = api.post(
        f"/api/v1/admissions/tests/{test_id}/assignments/", {"application": str(app.pk)}
    )
    assert seated.status_code == 201, seated.content
    scored = api.patch(f"/api/v1/admissions/assignments/{seated.json()['id']}/", {"score": "77"})
    assert scored.status_code == 200, scored.content
    [row] = api.get(f"/api/v1/admissions/tests/{test_id}/assignments/").json()
    assert (row["applicant_name"], row["score"]) == ("Ana", "77.00")
    preview = api.get(f"/api/v1/admissions/targets/{target.pk}/merit/").json()
    assert [r["applicant_name"] for r in preview["preview"]] == ["Ana"]
    assert preview["published"] is None
    publish = f"/api/v1/admissions/targets/{target.pk}/merit/publish/"
    assert api.post(publish).status_code == 403  # step-up needed
    api.step_up(head)
    assert api.post(publish).status_code == 201
    published = api.get(f"/api/v1/admissions/targets/{target.pk}/merit/").json()["published"]
    assert published["ranking"][0]["applicant_name"] == "Ana"
    offers = api.post(f"/api/v1/admissions/targets/{target.pk}/merit/offers/")
    assert [a["status"] for a in offers.json()] == ["offered"]
    outsider = make_user("south-head@example.com", mfa=True)
    grant_role(org.tenant, outsider.user, "institution_admin", institution=org.south)
    other = Api(host=tenant_host(org.tenant))
    other.login(outsider, expect="authenticated")
    assert other.get(f"/api/v1/admissions/tests/{test_id}/assignments/").status_code == 404
    assert other.get(f"/api/v1/admissions/targets/{target.pk}/merit/").status_code == 404
