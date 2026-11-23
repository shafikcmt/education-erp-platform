"""Admissions services (Phase 6 M4; ADR-065).

Plain functions with an explicit ``actor``: each re-checks its permission in the institution's
scope (uncached), validates and audits. Applications are validated by the cycle's published
Studio form (visibility and required fields decided on the server); custom values land in
``extra``. A cycle's workflow (if any) runs the review; the decision itself (offer or reject)
needs ``admissions.application.decide`` and, with a workflow, a finished request. Accepting an
offer calls ``ADMISSIONS_ACCEPTED_HANDLERS`` after commit (Phase 7 creates the student there).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone
from django.utils.module_loading import import_string

from apps.admissions.models import Application, Cycle, CycleTarget, Inquiry
from apps.audit.services import record
from apps.core.tenancy import require_tenant
from apps.rbac.engine import ScopeTarget, require_perm

if TYPE_CHECKING:
    from apps.identity.models import User

ENTITY, SUBJECT, MERIT = "admissions.application", "admissions.application", "admissions.merit"
INQUIRY, CYCLE = "admissions.inquiry.manage", "admissions.cycle.manage"
REVIEW, DECIDE = "admissions.application.review", "admissions.application.decide"
PROMOTED = ("applicant_name", "applicant_email", "applicant_phone", "date_of_birth")
OPEN_REVIEW = (Application.Status.SUBMITTED, Application.Status.UNDER_REVIEW,
               Application.Status.EVALUATED)  # fmt: skip
HOLDS_SEAT = (Application.Status.OFFERED, Application.Status.ACCEPTED)


def target_of(institution_id: Any) -> ScopeTarget:
    return ScopeTarget(require_tenant().id, institution_id)


def _authorise(actor: User, code: str, institution_id: Any) -> None:
    require_perm(actor, code, target=target_of(institution_id), use_cache=False)


def _audit(action: str, actor: Any, request: HttpRequest | None, obj: Any, **metadata: Any) -> None:
    record(
        action,
        actor=actor,
        request=request,
        target_type=f"admissions.{type(obj).__name__.lower()}",
        target_id=obj.pk,
        metadata=metadata,
    )


def _institution(institution: Any) -> Any:
    from apps.tenancy.models import Institution

    row = Institution.objects.filter(pk=getattr(institution, "pk", institution)).first()
    if row is None or row.archived_at is not None:
        raise ValidationError({"institution": "Unknown institution."})
    return row


# --------------------------------------------------------------------------- inquiries
INQUIRY_FIELDS = frozenset({"name", "phone", "email", "interest", "source", "status",
                            "assigned_to", "follow_up_on", "notes"})  # fmt: skip


def _inquiry_values(values: dict[str, Any]) -> dict[str, Any]:
    unknown = set(values) - INQUIRY_FIELDS
    if unknown:
        raise ValidationError(dict.fromkeys(sorted(unknown), "Unknown field."))
    if values.get("email"):
        validate_email(values["email"])
    if "assigned_to" in values and values["assigned_to"] is not None:
        from apps.tenancy.models import Membership

        member = Membership.objects.filter(pk=values["assigned_to"]).first()
        if member is None or member.status != Membership.Status.ACTIVE:
            raise ValidationError({"assigned_to": "Assign an active member."})
        values = {**values, "assigned_to": member}
    return values


@transaction.atomic
def create_inquiry(
    *, actor: User, institution: Any, values: dict[str, Any], request: HttpRequest | None = None
) -> Inquiry:
    inst = _institution(institution)
    _authorise(actor, INQUIRY, inst.pk)
    cleaned = _inquiry_values(values)
    if not (cleaned.get("phone") or cleaned.get("email")):
        raise ValidationError({"phone": "Give a phone number or an email address."})
    inquiry = Inquiry(institution=inst, created_by=actor.pk, **cleaned)
    inquiry.full_clean(exclude=["tenant"], validate_constraints=False)
    inquiry.save()
    _audit("admissions.inquiry.created", actor, request, inquiry, source=inquiry.source)
    return inquiry


@transaction.atomic
def update_inquiry(
    *, actor: User, inquiry: Inquiry, changes: dict[str, Any], request: HttpRequest | None = None
) -> Inquiry:
    inquiry = Inquiry.objects.select_for_update().get(pk=inquiry.pk)
    _authorise(actor, INQUIRY, inquiry.institution_id)
    for field, value in _inquiry_values(changes).items():
        setattr(inquiry, field, value)
    if not (inquiry.phone or inquiry.email):
        raise ValidationError({"phone": "Give a phone number or an email address."})
    inquiry.updated_by = actor.pk
    inquiry.full_clean(exclude=["tenant"], validate_constraints=False)
    inquiry.save()
    _audit("admissions.inquiry.updated", actor, request, inquiry, fields=",".join(sorted(changes)))
    return inquiry


# --------------------------------------------------------------------------- cycles
def _check_bindings(cycle: Cycle) -> None:
    """Every Studio artefact a cycle names must be published and fit admissions."""
    from apps.customization import versioning
    from apps.customization.models import (
        FormDefinition,
        NumberingSequence,
        RuleDefinition,
        WorkflowDefinition,
    )

    form = versioning.published(FormDefinition, cycle.form_key)
    if form is None or form.entity != ENTITY:
        raise ValidationError({"form_key": "Choose a published application form."})
    if cycle.workflow_key:
        flow = versioning.published(WorkflowDefinition, cycle.workflow_key)
        if flow is None or flow.subject != SUBJECT:
            raise ValidationError({"workflow_key": "Choose a published application workflow."})
    if cycle.merit_rule_key:
        rule = versioning.published(RuleDefinition, cycle.merit_rule_key)
        if rule is None or rule.namespace != MERIT:
            raise ValidationError({"merit_rule_key": "Choose a published merit rule."})
    if (
        cycle.numbering_key
        and not NumberingSequence.objects.filter(
            key=cycle.numbering_key, archived_at__isnull=True
        ).exists()
    ):
        raise ValidationError({"numbering_key": "Unknown numbering sequence."})


@transaction.atomic
def create_cycle(
    *,
    actor: User,
    institution: Any,
    year: Any,
    code: str,
    name: str,
    opens_on: dt.date,
    closes_on: dt.date,
    form_key: str,
    workflow_key: str = "",
    merit_rule_key: str = "",
    numbering_key: str = "",
    fee_amount: Decimal | None = None,
    fee_currency: str = "",
    name_i18n: dict[str, str] | None = None,
    request: HttpRequest | None = None,
) -> Cycle:
    from apps.academics.models import AcademicYear

    inst = _institution(institution)
    _authorise(actor, CYCLE, inst.pk)
    year_row = AcademicYear.objects.filter(pk=getattr(year, "pk", year), institution=inst).first()
    if year_row is None or year_row.status == AcademicYear.Status.CLOSED:
        raise ValidationError({"year": "Choose an open academic year of this institution."})
    if opens_on > closes_on:
        raise ValidationError({"closes_on": "The cycle closes after it opens."})
    if (fee_amount is None) != (not fee_currency):
        raise ValidationError({"fee_currency": "A fee needs an amount and a currency."})
    if Cycle.objects.filter(institution=inst, code=code).exists():
        raise ValidationError({"code": "This code is already used."})
    cycle = Cycle(
        institution=inst,
        year=year_row,
        code=code,
        name=name,
        name_i18n=name_i18n or {},
        opens_on=opens_on,
        closes_on=closes_on,
        form_key=form_key,
        workflow_key=workflow_key,
        merit_rule_key=merit_rule_key,
        numbering_key=numbering_key,
        fee_amount=fee_amount,
        fee_currency=fee_currency.upper(),
        created_by=actor.pk,
    )
    _check_bindings(cycle)
    cycle.full_clean(exclude=["tenant"], validate_constraints=False)
    cycle.save()
    _audit("admissions.cycle.created", actor, request, cycle, ref=code)
    return cycle


@transaction.atomic
def add_target(
    *, actor: User, cycle: Cycle, unit: Any, capacity: int, request: HttpRequest | None = None
) -> CycleTarget:
    from apps.academics.models import Unit

    cycle = Cycle.objects.select_for_update().get(pk=cycle.pk)
    _authorise(actor, CYCLE, cycle.institution_id)
    if cycle.status not in (Cycle.Status.DRAFT, Cycle.Status.OPEN):
        raise ValidationError({"cycle": "Targets change only while the cycle is draft or open."})
    unit_row = Unit.objects.filter(
        pk=getattr(unit, "pk", unit), institution_id=cycle.institution_id, archived_at__isnull=True
    ).first()
    if unit_row is None:
        raise ValidationError({"unit": "Choose a unit of this institution."})
    if capacity < 1:
        raise ValidationError({"capacity": "Capacity is at least one seat."})
    if CycleTarget.objects.filter(cycle=cycle, unit=unit_row).exists():
        raise ValidationError({"unit": "This unit is already a target."})
    target = CycleTarget.objects.create(
        institution_id=cycle.institution_id, cycle=cycle, unit=unit_row, capacity=capacity,
        created_by=actor.pk,
    )  # fmt: skip
    _audit("admissions.cycle.target_added", actor, request, cycle, capacity=capacity)
    return target


@transaction.atomic
def set_cycle_status(
    *, actor: User, cycle: Cycle, status: str, request: HttpRequest | None = None
) -> Cycle:
    cycle = Cycle.objects.select_for_update().get(pk=cycle.pk)
    _authorise(actor, CYCLE, cycle.institution_id)
    allowed: dict[str, set[str]] = {
        Cycle.Status.DRAFT: {Cycle.Status.OPEN},
        Cycle.Status.OPEN: {Cycle.Status.CLOSED},
        Cycle.Status.CLOSED: {Cycle.Status.OPEN, Cycle.Status.ARCHIVED},
    }
    if status not in allowed.get(cycle.status, set()):
        raise ValidationError({"status": f"A {cycle.status} cycle can't become {status}."})
    if status == Cycle.Status.OPEN:
        if not CycleTarget.objects.filter(cycle=cycle).exists():
            raise ValidationError({"status": "Add at least one target first."})
        _check_bindings(cycle)  # artefacts may have changed since the cycle was created
    cycle.status, cycle.updated_by = status, actor.pk
    cycle.save(update_fields=["status", "updated_by", "updated_at"])
    _audit("admissions.cycle.status_changed", actor, request, cycle, status=status)
    return cycle


# --------------------------------------------------------------------------- applications
def _split(cycle: Cycle, values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate by the cycle's form (server-side visibility and required fields), then the
    formats of the core values the platform relies on."""
    from apps.customization.forms import validate_submission

    cleaned = validate_submission(cycle.form_key, values)
    core, custom = dict(cleaned["core"]), dict(cleaned["custom"])
    errors: dict[str, str] = {}
    name = str(core.get("applicant_name") or "").strip()
    if not name:
        errors["applicant_name"] = "The applicant's name is required."
    elif len(name) > 160:
        errors["applicant_name"] = "At most 160 characters."
    if core.get("applicant_email"):
        try:
            validate_email(str(core["applicant_email"]))
        except ValidationError:
            errors["applicant_email"] = "Enter a valid email address."
    if core.get("date_of_birth"):
        try:
            core["date_of_birth"] = dt.date.fromisoformat(str(core["date_of_birth"]))
        except ValueError:
            errors["date_of_birth"] = "Use the date format YYYY-MM-DD."
    for key, value in core.items():
        if key not in PROMOTED and (not isinstance(value, str) or len(value) > 300):
            errors[key] = "Use text of at most 300 characters."
    if errors:
        raise ValidationError(errors)
    return core, custom


def _target(cycle: Cycle, target: Any) -> CycleTarget:
    row = CycleTarget.objects.filter(pk=getattr(target, "pk", target), cycle=cycle).first()
    if row is None:
        raise ValidationError({"target": "Choose a target of this cycle."})
    return row


def submit(application: Application, *, actor: Any) -> Application:
    """Number it, mark it submitted and start the cycle's workflow (inside the transaction)."""
    from apps.customization import numbering, workflows

    cycle = Cycle.objects.get(pk=application.cycle_id)
    if cycle.numbering_key:
        from apps.tenancy.models import Institution

        application.number = numbering.allocate(
            cycle.numbering_key, institution=Institution.objects.get(pk=cycle.institution_id)
        )
    application.status, application.submitted_at = Application.Status.SUBMITTED, timezone.now()
    application.save()
    if cycle.workflow_key and actor is not None:
        instance = workflows.start(
            actor=actor,
            key=cycle.workflow_key,
            subject_id=application.pk,
            context={"subject.source": application.source},
            target=target_of(cycle.institution_id),
        )
        application.workflow_instance_id = instance.pk
        application.save(update_fields=["workflow_instance_id", "updated_at"])
    return application


@transaction.atomic
def create_application(
    *,
    actor: User,
    cycle: Cycle,
    target: Any,
    values: dict[str, Any],
    request: HttpRequest | None = None,
) -> Application:
    """Staff enter an application on an applicant's behalf (same validation as the public form)."""
    cycle = Cycle.objects.get(pk=cycle.pk)
    _authorise(actor, REVIEW, cycle.institution_id)
    if cycle.status != Cycle.Status.OPEN:
        raise ValidationError({"cycle": "Applications are taken while the cycle is open."})
    target_row = _target(cycle, target)
    core, custom = _split(cycle, values)
    application = Application(
        institution_id=cycle.institution_id,
        cycle=cycle,
        target=target_row,
        source=Application.Source.STAFF,
        extra=custom,
        core={k: v for k, v in core.items() if k not in PROMOTED},
        created_by=actor.pk,
        **{k: core.get(k) or ("" if k != "date_of_birth" else None) for k in PROMOTED},
    )
    application = submit(application, actor=actor)
    _audit("admissions.application.submitted", actor, request, application, source="staff")
    return application


def _locked(application: Application) -> Application:
    return Application.objects.select_for_update().get(pk=application.pk)


@transaction.atomic
def start_review(
    *, actor: User, application: Application, request: HttpRequest | None = None
) -> Application:
    """Built-in path (cycles without a workflow): submitted → under review."""
    application = _locked(application)
    _authorise(actor, REVIEW, application.institution_id)
    if application.workflow_instance_id is not None:
        raise ValidationError({"status": "This application is reviewed through its workflow."})
    if application.status != Application.Status.SUBMITTED:
        raise ValidationError({"status": "Only submitted applications go into review."})
    application.status, application.updated_by = Application.Status.UNDER_REVIEW, actor.pk
    application.save(update_fields=["status", "updated_by", "updated_at"])
    _audit("admissions.application.status_changed", actor, request, application,
           status=application.status)  # fmt: skip
    return application


def _workflow_finished(application: Application) -> bool:
    from apps.customization.models import WorkflowInstance

    if application.workflow_instance_id is None:
        return True
    return WorkflowInstance.objects.filter(
        pk=application.workflow_instance_id, finished_at__isnull=False
    ).exists()


@transaction.atomic
def decide(
    *,
    actor: User,
    application: Application,
    decision: str,
    note: str = "",
    request: HttpRequest | None = None,
) -> Application:
    """Offer a seat (within the target's capacity) or reject."""
    application = _locked(application)
    _authorise(actor, DECIDE, application.institution_id)
    if decision not in (Application.Status.OFFERED, Application.Status.REJECTED):
        raise ValidationError({"decision": "Offer or reject."})
    if application.status not in OPEN_REVIEW:
        raise ValidationError({"status": "This application is not awaiting a decision."})
    if not _workflow_finished(application):
        raise ValidationError({"status": "Finish the review workflow first."})
    if decision == Application.Status.OFFERED:
        target = CycleTarget.objects.select_for_update().get(pk=application.target_id)
        taken = Application.objects.filter(target=target, status__in=HOLDS_SEAT).count()
        if taken >= target.capacity:
            raise ValidationError({"decision": "No seat left in this target."})
    application.status, application.decision_note = decision, note[:500]
    application.decided_at, application.updated_by = timezone.now(), actor.pk
    application.save()
    _audit("admissions.application.decided", actor, request, application, decision=decision)
    return application


def _accepted_handlers(tenant_id: str, application_id: str) -> None:
    for path in getattr(settings, "ADMISSIONS_ACCEPTED_HANDLERS", []):
        import_string(path)(tenant_id=tenant_id, application_id=application_id)


def respond_to_offer(
    application: Application, *, accept: bool, actor: Any, request: HttpRequest | None
) -> Application:
    """Record the applicant's answer (inside the transaction). Accepting queues the handlers."""
    application = _locked(application)
    if application.status != Application.Status.OFFERED:
        raise ValidationError({"status": "There is no open offer."})
    application.status = Application.Status.ACCEPTED if accept else Application.Status.DECLINED
    application.responded_at = timezone.now()
    application.save(update_fields=["status", "responded_at", "updated_at"])
    _audit("admissions.application.offer_answered", actor, request, application,
           accepted=accept)  # fmt: skip
    if accept:
        tenant_id, app_id = str(application.tenant_id), str(application.pk)
        transaction.on_commit(lambda: _accepted_handlers(tenant_id, app_id))
    return application


@transaction.atomic
def record_offer_response(
    *, actor: User, application: Application, accept: bool, request: HttpRequest | None = None
) -> Application:
    """Staff record an answer given on paper or by phone (the status link follows in M5)."""
    _authorise(actor, DECIDE, application.institution_id)
    return respond_to_offer(application, accept=accept, actor=actor, request=request)
