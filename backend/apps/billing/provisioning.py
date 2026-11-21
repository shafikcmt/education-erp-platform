"""Provisioning hook (Phase 4 M3; ADR-054 Q2): a new tenant starts on the ``trial`` plan when
the owner has created that plan with ``trial_days``. Plans are data: without such a plan the
tenant simply has platform modules until a plan is assigned."""

from __future__ import annotations

import structlog

from apps.billing.models import Plan
from apps.billing.services import start_trial

logger = structlog.get_logger("erp.billing")
TRIAL_PLAN = "trial"


def start_trial_plan(tenant: object, actor: object, request: object = None) -> None:
    plan = Plan.objects.filter(code=TRIAL_PLAN, archived_at__isnull=True).first()
    if plan is None or not plan.trial_days:
        return
    try:
        start_trial(
            actor=actor,  # type: ignore[arg-type]
            tenant_id=tenant.pk,  # type: ignore[attr-defined]
            plan_code=TRIAL_PLAN,
            days=int(plan.trial_days),
            reason="Trial plan at provisioning (ADR-054)",
            request=request,  # type: ignore[arg-type]
            scope_open=True,
        )
    except Exception:  # the tenant stays usable with platform modules; logged for follow-up
        logger.exception("billing.trial_at_provisioning_failed", tenant_id=str(tenant.pk))  # type: ignore[attr-defined]
