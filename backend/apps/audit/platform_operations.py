"""Auditor for ``apps.core.tenancy.platform.platform_scope`` (ADR-043, plan §6.4).

Configured as ``settings.TENANCY_PLATFORM_AUDITOR`` so that ``core`` never imports ``audit``.
Writes ``platform.operation.started`` / ``platform.operation.completed`` to the **platform**
log (``tenant_id`` NULL). The completed event carries the outcome and the number of tenants the
operation touched; a single targeted tenant is also recorded as the event target.
"""

from typing import Any

from apps.audit.models import ActorType, Outcome
from apps.audit.services import record


def record_platform_operation(handle: Any, *, stage: str, succeeded: bool) -> None:
    actor = handle.actor
    is_user = bool(getattr(actor, "is_authenticated", False))
    metadata: dict[str, Any] = {
        "operation": handle.operation_id,
        "reason": handle.reason,
        "permission": handle.permission or "",
    }
    target_id = None
    if stage == "completed":
        metadata["tenant_count"] = len(handle.tenant_ids)
        if len(handle.tenant_ids) == 1:
            target_id = next(iter(handle.tenant_ids))
    record(
        f"platform.operation.{stage}",
        outcome=Outcome.SUCCESS if succeeded else Outcome.FAILURE,
        actor=actor if is_user else None,
        actor_type=ActorType.USER if is_user else ActorType.SYSTEM,
        target_type="tenant" if target_id else "",
        target_id=target_id,
        metadata=metadata,
    )
