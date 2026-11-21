"""Tenant Celery tasks (Phase 3 M7; plan §8.5 C1-C10; ADR-042).

A tenant task is called with ``tenant_id=<uuid>`` (keyword, explicit: nothing is inherited from
the caller, C9). Every attempt (first run or retry, C3) opens its own ``tenant_atomic`` for
that tenant, checks the tenant in the registry inside it, runs the body there and always
resets in ``finally``: an exception or a soft time limit rolls everything back (C2, C4), and
the next task on the same worker starts clean (C1).

Refused before the body runs (C7): a missing or malformed id, an unknown tenant, a tenant
whose status the task doesn't accept (``active`` only, unless declared otherwise), and (Phase 4
M4) a tenant not entitled to the task's ``module``.

Run eagerly from inside a request of the SAME tenant (tests, ``apply()``), the task still opens
its own transaction; from a request of ANOTHER tenant it raises ``TenantContextConflict`` (C6).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from celery import shared_task

from apps.core.tasking import TENANT, DeclaredTask
from apps.core.tenancy import TenantContext, tenant_atomic, validate_tenant_id
from apps.core.tenancy.exceptions import InvalidTenantId
from apps.tenancy.models import Tenant
from apps.tenancy.rules import TenantStatus


class TenantTaskRefused(Exception):  # noqa: N818 - refusal, not a programming error
    """The task was not run for this tenant (missing/unknown id or unaccepted status)."""


class TenantTask(DeclaredTask):
    abstract = True
    erp_kind = TENANT
    accepted_statuses: frozenset[str] = frozenset({TenantStatus.ACTIVE})
    module_code = ""  # Phase 4 M4: refused unless the tenant is entitled to this module

    def run_declared(self, *args: Any, **kwargs: Any) -> Any:
        raw = kwargs.get("tenant_id")
        if raw is None:
            raise TenantTaskRefused(f"{self.name} needs tenant_id= (keyword, explicit).")
        try:
            tenant_id = validate_tenant_id(raw)
        except InvalidTenantId as exc:
            raise TenantTaskRefused(f"{self.name}: invalid tenant id.") from exc
        kwargs["tenant_id"] = tenant_id
        with tenant_atomic(TenantContext(id=tenant_id)):
            # Self-scoped registry: inside the tenant's transaction only its own row exists.
            status = Tenant.objects.filter(pk=tenant_id).values_list("status", flat=True).first()
            if status is None or status not in self.accepted_statuses:
                raise TenantTaskRefused(
                    f"{self.name}: tenant not available ({status or 'unknown'})."
                )
            if self.module_code:
                from apps.module_registry.entitlements import is_entitled

                if not is_entitled(self.module_code):
                    raise TenantTaskRefused(f"{self.name}: module {self.module_code} not entitled.")
            return super().run_declared(*args, **kwargs)


def tenant_task(
    *,
    name: str,
    statuses: Iterable[str] = (TenantStatus.ACTIVE,),
    module: str = "",
    **options: Any,
) -> Callable[..., Any]:
    """Declare a tenant task. ``statuses``: tenant statuses the task may run in (C7).
    ``module``: the module the task belongs to; refused for tenants not entitled to it
    (Phase 4 M4, ADR-052)."""
    accepted = frozenset(statuses)
    unknown = accepted - {code for code, _ in TenantStatus.CHOICES}
    if not accepted or unknown:
        raise ValueError(f"Invalid tenant statuses for {name}: {sorted(unknown) or 'none'}")
    # ``typing=False``: a missing ``tenant_id`` must reach the explicit refusal above (C7)
    # instead of Celery's generic argument check.
    decorator: Callable[..., Any] = shared_task(
        name=name,
        base=TenantTask,
        accepted_statuses=accepted,
        module_code=module,
        typing=False,
        **options,
    )
    return decorator
