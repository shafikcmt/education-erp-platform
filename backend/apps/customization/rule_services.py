"""Rule drafts, tests and publishing (Phase 5 M3; ADR-055).

A rule is checked statically on every save. Publishing needs ``customization.config.publish``
(MFA + step-up at the API) and at least one test case; every case must pass. Published
versions are immutable; a new draft creates the next version.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError

from apps.audit.services import record
from apps.core.tenancy import require_tenant
from apps.customization import versioning
from apps.customization.models import Lifecycle, RuleDefinition
from apps.customization.registry import declared_namespaces
from apps.customization.rules import Namespace, RuleError, check, evaluate
from apps.rbac.engine import ScopeTarget, require_perm

if TYPE_CHECKING:
    from django.http import HttpRequest

    from apps.identity.models import User

MANAGE, PUBLISH = "customization.rule.manage", "customization.config.publish"
MAX_CASES = 50


def namespace(code: str) -> Namespace:
    spec = declared_namespaces().get(code)
    if spec is None:
        raise ValidationError({"namespace": "Unknown rule namespace."})
    return spec


def _target() -> ScopeTarget:
    return ScopeTarget(require_tenant().id)


def _normalise(value: Any) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int | float | Decimal):
        return Decimal(repr(value)) if isinstance(value, float) else Decimal(value)
    if isinstance(value, list):
        return [_normalise(v) for v in value]
    return value


def _check_cases(cases: Any) -> list[dict[str, Any]]:
    if not isinstance(cases, list) or len(cases) > MAX_CASES:
        raise ValidationError({"test_cases": f"Give up to {MAX_CASES} test cases."})
    for case in cases:
        if (
            not isinstance(case, dict)
            or set(case) != {"context", "expected"}
            or not isinstance(case["context"], dict)
        ):
            raise ValidationError({"test_cases": "Each case is {context: {...}, expected: …}."})
    return cases


def run_cases(spec: Namespace, rule: Any, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Evaluate every case; report results (never raises for a failing case)."""
    results = []
    for index, case in enumerate(cases):
        try:
            got = evaluate(rule, spec, case["context"])
            ok = _normalise(got) == _normalise(case["expected"])
            results.append({"case": index, "passed": ok, "result": got, "error": ""})
        except RuleError as exc:
            results.append({"case": index, "passed": False, "result": None, "error": str(exc)})
    return results


def save_rule_draft(
    *,
    actor: User,
    namespace_code: str,
    key: str,
    name: str,
    rule: Any,
    test_cases: Any = (),
    request: HttpRequest | None = None,
) -> RuleDefinition:
    require_perm(actor, MANAGE, target=_target(), use_cache=False)
    spec = namespace(namespace_code)
    try:
        check(rule, spec)
    except RuleError as exc:
        raise ValidationError({"rule": str(exc)}) from None
    cases = _check_cases(list(test_cases))
    current = versioning.published(RuleDefinition, key)
    if current is not None and current.namespace != namespace_code:
        raise ValidationError({"namespace": "A rule keeps its namespace."})
    draft = versioning.draft_for(RuleDefinition, key, actor.pk)
    draft.namespace, draft.name, draft.rule, draft.test_cases = namespace_code, name, rule, cases
    draft.updated_by = actor.pk
    try:
        draft.full_clean(exclude=["tenant"])
    except ValidationError as exc:
        raise ValidationError(exc.message_dict) from None
    draft.save()
    record(
        "customization.rule.draft_saved",
        actor=actor,
        request=request,
        target_type="customization.rule",
        target_id=draft.pk,
        metadata={"key": key, "namespace": namespace_code, "number": draft.number},
    )
    return draft


def publish_rule(*, actor: User, key: str, request: HttpRequest | None = None) -> RuleDefinition:
    require_perm(actor, PUBLISH, target=_target(), use_cache=False)
    draft = versioning.draft_or_none(RuleDefinition, key)
    if draft is None:
        raise ValidationError({"key": "There is no draft of this rule."})
    spec = namespace(draft.namespace)
    if not draft.test_cases:
        raise ValidationError({"test_cases": "Add at least one test case before publishing."})
    failed = [r for r in run_cases(spec, draft.rule, draft.test_cases) if not r["passed"]]
    if failed:
        raise ValidationError({"test_cases": f"{len(failed)} test case(s) fail."})
    versioning.activate(RuleDefinition, draft, actor.pk)
    record(
        "customization.rule.published",
        actor=actor,
        request=request,
        target_type="customization.rule",
        target_id=draft.pk,
        metadata={"key": key, "namespace": draft.namespace, "number": draft.number},
    )
    return draft


def evaluate_published(key: str, namespace_code: str, context: dict[str, Any]) -> Any:
    """Evaluate the published version of ``key`` (used by forms and workflows)."""
    row = RuleDefinition.objects.filter(
        key=key, namespace=namespace_code, status=Lifecycle.PUBLISHED
    ).first()
    if row is None:
        raise RuleError(f"No published rule {key!r} in {namespace_code}.")
    return evaluate(row.rule, namespace(namespace_code), context)
