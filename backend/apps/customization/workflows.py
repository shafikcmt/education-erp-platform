"""Declarative approval workflows (Phase 5 M4; CUSTOMIZATION_ENGINE.md §4.4).

A spec is ``{"states": [{"key", "labels", "final"?}], "initial", "start_permission",
"transitions": [{"key", "from": [...], "to", "labels", "permission", "guard"?, "notify"?}],
"sla_hours": {state: hours}}``. Guards run in the rules sandbox (``customization.workflow_guard``,
variables ``subject.*`` and ``today``). Every transition checks its permission (uncached) in
the given scope, evaluates its guard against the instance context, appends a step, sets the SLA
due time and notifies the starter and the members who can act next. Instances pin the
definition version they started with; one open instance per subject and definition.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.audit.services import record
from apps.core.tenancy import require_tenant
from apps.customization import versioning
from apps.customization.models import WorkflowDefinition, WorkflowInstance, WorkflowStep
from apps.customization.registry import declared_namespaces, declared_subjects
from apps.customization.rules import RuleError, check, evaluate
from apps.rbac.engine import ScopeTarget, require_perm
from apps.rbac.registry import declared_permissions

if TYPE_CHECKING:
    from django.http import HttpRequest

    from apps.identity.models import User

MANAGE, PUBLISH = "customization.workflow.manage", "customization.config.publish"
GUARD = "customization.workflow_guard"
_KEY = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


def _tenant_target() -> ScopeTarget:
    return ScopeTarget(require_tenant().id)


def validate_spec(subject: str, spec: Any) -> dict[str, Any]:
    if subject not in declared_subjects():
        raise ValidationError({"subject": "Workflows run on declared subjects only."})
    if not isinstance(spec, dict):
        raise ValidationError({"spec": "A workflow spec is an object."})
    states = spec.get("states")
    if not isinstance(states, list) or not 2 <= len(states) <= 30:
        raise ValidationError({"spec": "Give 2-30 states."})
    keys = [s.get("key") for s in states if isinstance(s, dict)]
    if (
        len(keys) != len(states)
        or len(set(keys)) != len(keys)
        or not all(isinstance(k, str) and _KEY.match(k) for k in keys)
    ):
        raise ValidationError({"spec": "State keys are unique identifiers."})
    final = {s["key"] for s in states if s.get("final")}
    if not final:
        raise ValidationError({"spec": "At least one state is final."})
    if spec.get("initial") not in keys or spec.get("initial") in final:
        raise ValidationError({"spec": "The initial state is a non-final state."})
    known = declared_permissions()
    if spec.get("start_permission") not in known:
        raise ValidationError({"spec": "start_permission must be a known permission."})
    transitions = spec.get("transitions")
    if not isinstance(transitions, list) or not 1 <= len(transitions) <= 60:
        raise ValidationError({"spec": "Give 1-60 transitions."})
    namespace = declared_namespaces()[GUARD]
    seen: set[str] = set()
    for t in transitions:
        if not isinstance(t, dict) or not _KEY.match(str(t.get("key", ""))) or t["key"] in seen:
            raise ValidationError({"spec": "Transition keys are unique identifiers."})
        seen.add(t["key"])
        sources = t.get("from")
        if (
            not isinstance(sources, list)
            or not sources
            or any(s not in keys or s in final for s in sources)
        ):
            raise ValidationError({"spec": f"{t['key']}: 'from' lists non-final states."})
        if t.get("to") not in keys:
            raise ValidationError({"spec": f"{t['key']}: unknown target state."})
        if t.get("permission") not in known:
            raise ValidationError({"spec": f"{t['key']}: unknown permission."})
        if "guard" in t:
            try:
                check(t["guard"], namespace)
            except RuleError as exc:
                raise ValidationError({"spec": f"{t['key']}: {exc}"}) from None
    sla = spec.get("sla_hours", {})
    if not isinstance(sla, dict) or any(
        s not in keys or s in final or not isinstance(h, int) or not 1 <= h <= 8760
        for s, h in sla.items()
    ):
        raise ValidationError({"spec": "sla_hours maps non-final states to 1-8760 hours."})
    reachable = {spec["initial"]}
    changed = True
    while changed:
        changed = False
        for t in transitions:
            if set(t["from"]) & reachable and t["to"] not in reachable:
                reachable.add(t["to"])
                changed = True
    if not final & reachable:
        raise ValidationError({"spec": "No final state is reachable from the initial state."})
    return spec


def save_workflow_draft(
    *,
    actor: User,
    key: str,
    subject: str,
    name: str,
    spec: Any,
    request: HttpRequest | None = None,
) -> WorkflowDefinition:
    require_perm(actor, MANAGE, target=_tenant_target(), use_cache=False)
    current = versioning.published(WorkflowDefinition, key)
    if current is not None and current.subject != subject:
        raise ValidationError({"subject": "A workflow keeps its subject."})
    validate_spec(subject, spec)
    draft = versioning.draft_for(WorkflowDefinition, key, actor.pk)
    draft.subject, draft.name, draft.spec, draft.updated_by = subject, name, spec, actor.pk
    try:
        draft.full_clean(exclude=["tenant"])
    except ValidationError as exc:
        raise ValidationError(exc.message_dict) from None
    draft.save()
    record(
        "customization.workflow.draft_saved",
        actor=actor,
        request=request,
        target_type="customization.workflow",
        target_id=draft.pk,
        metadata={"key": key, "subject": subject, "number": draft.number},
    )
    return draft


def publish_workflow(
    *, actor: User, key: str, request: HttpRequest | None = None
) -> WorkflowDefinition:
    require_perm(actor, PUBLISH, target=_tenant_target(), use_cache=False)
    draft = versioning.draft_or_none(WorkflowDefinition, key)
    if draft is None:
        raise ValidationError({"key": "There is no draft of this workflow."})
    validate_spec(draft.subject, draft.spec)
    versioning.activate(WorkflowDefinition, draft, actor.pk)
    record(
        "customization.workflow.published",
        actor=actor,
        request=request,
        target_type="customization.workflow",
        target_id=draft.pk,
        metadata={"key": key, "subject": draft.subject, "number": draft.number},
    )
    return draft


def _membership_id(user_id: Any) -> uuid.UUID | None:
    from apps.tenancy.models import Membership

    return (
        Membership.objects.filter(user_id=user_id, status=Membership.Status.ACTIVE)
        .values_list("pk", flat=True)
        .first()
    )


def _approvers(codes: set[str]) -> set[uuid.UUID]:
    """Active members holding any of ``codes`` through a live role assignment."""
    from apps.rbac.models import RoleAssignment
    from apps.tenancy.models import Membership
    from apps.tenancy.rbac_sources import live_assignments

    if not codes:
        return set()
    return set(
        RoleAssignment.objects.filter(
            live_assignments(),
            membership__status=Membership.Status.ACTIVE,
            role__role_permissions__permission__code__in=codes,
        )
        .values_list("membership_id", flat=True)
        .distinct()
    )


def _sla_due(spec: dict[str, Any], state: str, now: dt.datetime) -> dt.datetime | None:
    hours = spec.get("sla_hours", {}).get(state)
    return now + timedelta(hours=hours) if hours else None


def _notify_next(instance: WorkflowInstance, spec: dict[str, Any], title: str) -> None:
    from apps.notifications_core.services import notify

    codes = {t["permission"] for t in spec["transitions"] if instance.state in t["from"]}
    recipients = _approvers(codes)
    starter = _membership_id(instance.started_by)
    if starter is not None:
        recipients.add(starter)
    notify(recipients, kind="customization.workflow", title=title, link=f"/workflows/{instance.pk}")


def start(
    *,
    actor: User,
    key: str,
    subject_id: uuid.UUID,
    context: dict[str, Any] | None = None,
    target: ScopeTarget | None = None,
    request: HttpRequest | None = None,
) -> WorkflowInstance:
    definition = versioning.published(WorkflowDefinition, key)
    if definition is None:
        raise ValidationError({"workflow": "Unknown or unpublished workflow."})
    spec = definition.spec
    require_perm(
        actor, spec["start_permission"], target=target or _tenant_target(), use_cache=False
    )
    now = timezone.now()
    if WorkflowInstance.objects.filter(
        definition=definition, subject_id=subject_id, finished_at__isnull=True
    ).exists():
        raise ValidationError({"subject": "This subject already has an open request."})
    instance = WorkflowInstance.objects.create(
        definition=definition,
        subject=definition.subject,
        subject_id=subject_id,
        state=spec["initial"],
        context={k: v for k, v in (context or {}).items() if k.startswith("subject.")},
        started_by=actor.pk,
        entered_state_at=now,
        sla_due_at=_sla_due(spec, spec["initial"], now),
    )
    record(
        "customization.workflow.started",
        actor=actor,
        request=request,
        target_type="customization.workflow_instance",
        target_id=instance.pk,
        metadata={"key": key, "number": definition.number, "state": instance.state},
    )
    _notify_next(instance, spec, f"New request: {definition.name}")
    return instance


def transition(
    *,
    actor: User,
    instance_id: uuid.UUID,
    transition_key: str,
    note: str = "",
    target: ScopeTarget | None = None,
    today: dt.date | None = None,
    request: HttpRequest | None = None,
) -> WorkflowInstance:
    instance = WorkflowInstance.objects.select_for_update().filter(pk=instance_id).first()
    if instance is None:
        raise ValidationError({"instance": "Unknown request."})
    if instance.finished_at is not None:
        raise ValidationError({"instance": "This request is already finished."})
    definition = WorkflowDefinition.objects.get(pk=instance.definition_id)  # pinned version
    spec = definition.spec
    move = next((t for t in spec["transitions"] if t["key"] == transition_key), None)
    if move is None or instance.state not in move["from"]:
        raise ValidationError({"transition": "This action isn't available in the current state."})
    require_perm(actor, move["permission"], target=target or _tenant_target(), use_cache=False)
    if "guard" in move:
        context = {**instance.context, "today": today or dt.date.today()}
        try:
            allowed = evaluate(move["guard"], declared_namespaces()[GUARD], context)
        except RuleError:
            allowed = False  # a guard that can't decide refuses (fail closed)
        if allowed is not True:
            raise ValidationError({"transition": "The conditions for this action aren't met."})
    now = timezone.now()
    previous = instance.state
    instance.state, instance.entered_state_at = move["to"], now
    instance.sla_due_at, instance.sla_breached_at = _sla_due(spec, move["to"], now), None
    final = {s["key"] for s in spec["states"] if s.get("final")}
    if instance.state in final:
        instance.finished_at = now
    instance.save()
    WorkflowStep.objects.create(
        instance=instance,
        transition=transition_key,
        from_state=previous,
        to_state=instance.state,
        actor=actor.pk,
        note=note[:500],
    )
    record(
        "customization.workflow.transitioned",
        actor=actor,
        request=request,
        target_type="customization.workflow_instance",
        target_id=instance.pk,
        metadata={"transition": transition_key, "from": previous, "to": instance.state},
    )
    if move.get("notify", True):
        _notify_next(instance, spec, f"{definition.name}: {instance.state}")
    return instance


def mark_overdue(now: dt.datetime | None = None) -> int:
    """Flag open instances past their SLA and notify who can act (P24 tenant task)."""
    now = now or timezone.now()
    overdue = list(
        WorkflowInstance.objects.select_for_update().filter(
            finished_at__isnull=True, sla_breached_at__isnull=True, sla_due_at__lte=now
        )
    )
    for instance in overdue:
        instance.sla_breached_at = now
        instance.save(update_fields=["sla_breached_at", "updated_at"])
        definition = WorkflowDefinition.objects.get(pk=instance.definition_id)
        _notify_next(instance, definition.spec, f"Overdue: {definition.name}")
    return len(overdue)
