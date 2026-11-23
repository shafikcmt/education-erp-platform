"""Admission tests, scores, the merit list and offers by merit (Phase 6 M6; ADR-065).

* **Tests:** a cycle schedules tests (date and time, venue, capacity, maximum score). Seating an
  application gives it the next seat number and makes it ``test_scheduled``. When every test of
  an application has a score or is marked absent, the application becomes ``evaluated`` with the
  total score. Applications without tests can be marked evaluated directly.
* **Merit list:** evaluated applications of a target whose review (workflow) is finished are
  ranked by the cycle's merit rule (sandbox, ``Decimal``, namespace ``admissions.merit``) or,
  without a rule, by the total score. Ties are broken by the total score, then the submission
  time, then the number (the rule may build its own tie-breaks into the value). A rule that
  cannot be evaluated for an application stops the publication (fail closed).
* **Publishing** (``admissions.merit.publish``: MFA and step-up) freezes the ranking as a new
  version and records each application's rank.
* **Offers by merit** follow the latest published ranking up to the target's free seats. When an
  offer is declined, the next ranked application is offered the freed seat automatically
  (audited as a system action under the published list).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.http import HttpRequest
from django.utils import timezone

from apps.admissions.models import Application, Cycle, CycleTarget, MeritList, Test, TestAssignment
from apps.admissions.services import (
    DECIDE,
    HOLDS_SEAT,
    MERIT,
    REVIEW,
    _audit,
    _authorise,
    _locked,
    _workflow_finished,
)

if TYPE_CHECKING:
    from apps.identity.models import User

TESTS, PUBLISH = "admissions.test.manage", "admissions.merit.publish"
SEATABLE = (Application.Status.SUBMITTED, Application.Status.UNDER_REVIEW,
            Application.Status.TEST_SCHEDULED)  # fmt: skip
SCORABLE = (Application.Status.TEST_SCHEDULED, Application.Status.EVALUATED)


# --------------------------------------------------------------------------- tests
@transaction.atomic
def create_test(
    *,
    actor: User,
    cycle: Cycle,
    name: str,
    starts_at: dt.datetime,
    capacity: int,
    max_score: Decimal,
    venue: str = "",
    request: HttpRequest | None = None,
) -> Test:
    cycle = Cycle.objects.select_for_update().get(pk=cycle.pk)
    _authorise(actor, TESTS, cycle.institution_id)
    if cycle.status not in (Cycle.Status.DRAFT, Cycle.Status.OPEN, Cycle.Status.CLOSED):
        raise ValidationError({"cycle": "This cycle is archived."})
    errors: dict[str, str] = {}
    if not name.strip() or len(name) > 160:
        errors["name"] = "Give the test a name of at most 160 characters."
    if capacity < 1:
        errors["capacity"] = "Capacity is at least one seat."
    if max_score is None or Decimal(max_score) <= 0:
        errors["max_score"] = "The maximum score is above zero."
    if len(venue) > 200:
        errors["venue"] = "At most 200 characters."
    if errors:
        raise ValidationError(errors)
    test = Test.objects.create(
        institution_id=cycle.institution_id, cycle=cycle, name=name.strip(), starts_at=starts_at,
        venue=venue.strip(), capacity=capacity, max_score=Decimal(max_score), created_by=actor.pk,
    )  # fmt: skip
    _audit("admissions.test.created", actor, request, test, capacity=capacity)
    return test


@transaction.atomic
def assign_test(
    *, actor: User, test: Test, application: Application, request: HttpRequest | None = None
) -> TestAssignment:
    test = Test.objects.select_for_update().get(pk=test.pk)
    _authorise(actor, TESTS, test.institution_id)
    application = _locked(application)
    if application.cycle_id != test.cycle_id:
        raise ValidationError({"application": "Choose an application of this test's cycle."})
    if application.status not in SEATABLE:
        raise ValidationError({"application": "Only applications in review can sit a test."})
    if TestAssignment.objects.filter(test=test, application=application).exists():
        raise ValidationError({"application": "This application is already seated."})
    seats = TestAssignment.objects.filter(test=test)
    if seats.count() >= test.capacity:
        raise ValidationError({"test": "This test is full."})
    seat = (seats.aggregate(top=Max("seat"))["top"] or 0) + 1
    row = TestAssignment.objects.create(
        cycle_id=test.cycle_id, test=test, application=application, seat=seat,
        created_by=actor.pk,
    )  # fmt: skip
    if application.status != Application.Status.TEST_SCHEDULED:
        application.status, application.score = Application.Status.TEST_SCHEDULED, None
        application.updated_by = actor.pk
        application.save(update_fields=["status", "score", "updated_by", "updated_at"])
    _audit("admissions.test.assigned", actor, request, test, seat=seat)
    return row


def _settle(application: Application, actor: User, request: HttpRequest | None) -> None:
    """Evaluated once every test has a score or an absence; the score is the total."""
    rows = list(TestAssignment.objects.filter(application=application))
    if not rows or any(r.score is None and not r.absent for r in rows):
        if application.status == Application.Status.EVALUATED:
            application.status, application.score = Application.Status.TEST_SCHEDULED, None
            application.save(update_fields=["status", "score", "updated_at"])
        return
    total = sum((r.score or Decimal(0) for r in rows), Decimal(0))
    was = application.status
    application.status, application.score = Application.Status.EVALUATED, total
    application.updated_by = actor.pk
    application.save(update_fields=["status", "score", "updated_by", "updated_at"])
    if was != Application.Status.EVALUATED:
        _audit("admissions.application.evaluated", actor, request, application, tests=len(rows))


@transaction.atomic
def record_score(
    *,
    actor: User,
    assignment: TestAssignment,
    score: Decimal | None,
    absent: bool = False,
    request: HttpRequest | None = None,
) -> TestAssignment:
    row = TestAssignment.objects.select_for_update().get(pk=assignment.pk)
    test = Test.objects.get(pk=row.test_id)
    _authorise(actor, TESTS, test.institution_id)
    application = _locked(Application(pk=row.application_id))
    if application.status not in SCORABLE:
        raise ValidationError({"score": "Scores change only before a decision."})
    if absent and score is not None:
        raise ValidationError({"score": "An absent applicant has no score."})
    if score is not None and not (Decimal(0) <= Decimal(score) <= test.max_score):
        raise ValidationError({"score": f"Enter a score between 0 and {test.max_score}."})
    row.score = None if score is None else Decimal(score)
    row.absent, row.updated_by = absent, actor.pk
    row.scored_at = timezone.now() if (absent or score is not None) else None
    row.save(update_fields=["score", "absent", "scored_at", "updated_by", "updated_at"])
    _audit("admissions.test.scored", actor, request, test, absent=absent)
    _settle(application, actor, request)
    return row


@transaction.atomic
def mark_evaluated(
    *, actor: User, application: Application, request: HttpRequest | None = None
) -> Application:
    """For cycles without tests: an application in review is ready for the merit list."""
    application = _locked(application)
    _authorise(actor, REVIEW, application.institution_id)
    if application.status not in (Application.Status.SUBMITTED, Application.Status.UNDER_REVIEW):
        raise ValidationError({"status": "Only applications in review can be evaluated."})
    if TestAssignment.objects.filter(application=application).exists():
        raise ValidationError({"status": "Enter the test scores instead."})
    application.status, application.updated_by = Application.Status.EVALUATED, actor.pk
    application.save(update_fields=["status", "updated_by", "updated_at"])
    _audit("admissions.application.evaluated", actor, request, application, tests=0)
    return application


# --------------------------------------------------------------------------- merit
def _plain(value: Any) -> Any:
    """JSON values for the rules sandbox: numbers become ``Decimal`` (never floats)."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, str | Decimal | dt.date):
        return value
    return None  # lists and objects are not offered to rules


def merit_context(application: Application) -> dict[str, Any]:
    """The variables an ``admissions.merit`` rule may read (``application.*``, ``today``)."""
    context: dict[str, Any] = {"today": timezone.localdate()}
    values = {**application.core, **application.extra}
    for key, value in values.items():
        plain = _plain(value)
        if plain is not None or value is None:
            context[f"application.{key}"] = plain
    context.update(
        {
            "application.applicant_name": application.applicant_name,
            "application.date_of_birth": application.date_of_birth,
            "application.source": application.source,
            "application.score": application.score,
        }
    )
    return context


def _eligible(target: CycleTarget) -> list[Application]:
    rows = Application.objects.filter(target=target, status=Application.Status.EVALUATED)
    return [a for a in rows.order_by("submitted_at", "number") if _workflow_finished(a)]


def ranking(target: CycleTarget) -> list[dict[str, Any]]:
    """The current ranking (not saved). Raises ``ValidationError`` if the rule fails."""
    from apps.customization.rule_services import evaluate_published
    from apps.customization.rules import RuleError

    cycle = Cycle.objects.get(pk=target.cycle_id)
    scored: list[tuple[Decimal, Application]] = []
    for application in _eligible(target):
        if cycle.merit_rule_key:
            try:
                value = evaluate_published(cycle.merit_rule_key, MERIT, merit_context(application))
            except RuleError as exc:
                ref = application.number or str(application.pk)
                raise ValidationError({"merit": f"{ref}: {exc}"}) from None
        else:
            value = application.score or Decimal(0)
        scored.append((Decimal(value), application))
    far = dt.datetime.max.replace(tzinfo=dt.UTC)
    scored.sort(
        key=lambda pair: (
            -pair[0],
            -(pair[1].score or Decimal(0)),
            pair[1].submitted_at or far,
            pair[1].number,
        )
    )
    return [
        {
            "application": str(app.pk),
            "number": app.number,
            "applicant_name": app.applicant_name,
            "score": str(value),
            "total": str(app.score) if app.score is not None else "",
            "rank": index,
            "status": app.status,
        }
        for index, (value, app) in enumerate(scored, start=1)
    ]


def latest(target: CycleTarget) -> MeritList | None:
    return MeritList.objects.filter(target=target).order_by("-version").first()


@transaction.atomic
def publish(*, actor: User, target: CycleTarget, request: HttpRequest | None = None) -> MeritList:
    target = CycleTarget.objects.select_for_update().get(pk=target.pk)
    _authorise(actor, PUBLISH, target.institution_id)
    ranked = ranking(target)
    if not ranked:
        raise ValidationError({"merit": "No evaluated applications to rank yet."})
    cycle = Cycle.objects.get(pk=target.cycle_id)
    previous = latest(target)
    merit = MeritList.objects.create(
        institution_id=target.institution_id,
        cycle_id=target.cycle_id,
        target=target,
        version=(previous.version + 1) if previous else 1,
        ranking=[{k: v for k, v in row.items() if k != "applicant_name"} for row in ranked],
        rule_key=cycle.merit_rule_key,
        published_at=timezone.now(),
        created_by=actor.pk,
    )
    Application.objects.filter(target=target).exclude(merit_rank=None).update(merit_rank=None)
    for row in ranked:
        Application.objects.filter(pk=row["application"]).update(merit_rank=row["rank"])
    _audit("admissions.merit.published", actor, request, merit, version=merit.version,
           ranked=len(ranked))  # fmt: skip
    return merit


def _offer_next(target: CycleTarget, *, actor_id: Any) -> list[Application]:
    """Offer the free seats to the best-ranked waiting applications (target row locked)."""
    merit = latest(target)
    if merit is None:
        return []
    free = (
        target.capacity - Application.objects.filter(target=target, status__in=HOLDS_SEAT).count()
    )
    offered: list[Application] = []
    for row in merit.ranking:
        if free <= 0:
            break
        application = (
            Application.objects.select_for_update()
            .filter(pk=row["application"], status=Application.Status.EVALUATED)
            .first()
        )
        if application is None or not _workflow_finished(application):
            continue  # already decided, withdrawn or re-opened since publication
        application.status, application.decided_at = Application.Status.OFFERED, timezone.now()
        application.updated_by = actor_id
        application.save(update_fields=["status", "decided_at", "updated_by", "updated_at"])
        offered.append(application)
        free -= 1
    return offered


@transaction.atomic
def offer_by_merit(
    *, actor: User, target: CycleTarget, request: HttpRequest | None = None
) -> list[Application]:
    target = CycleTarget.objects.select_for_update().get(pk=target.pk)
    _authorise(actor, DECIDE, target.institution_id)
    merit = latest(target)
    if merit is None:
        raise ValidationError({"merit": "Publish a merit list first."})
    offered = _offer_next(target, actor_id=actor.pk)
    _audit("admissions.merit.offers_made", actor, request, merit, version=merit.version,
           offered=len(offered), via="staff")  # fmt: skip
    return offered


def after_decline(application: Application, request: HttpRequest | None) -> None:
    """A declined offer frees its seat: the next ranked applicant of a published list gets it."""
    target = CycleTarget.objects.select_for_update().get(pk=application.target_id)
    merit = latest(target)
    if merit is None:
        return
    offered = _offer_next(target, actor_id=None)
    if offered:
        _audit("admissions.merit.offers_made", None, request, merit, version=merit.version,
               offered=len(offered), via="decline")  # fmt: skip
