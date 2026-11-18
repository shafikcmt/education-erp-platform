"""Run platform maintenance once for the platform scope and once per tenant (Phase 3 M6;
plan §6.3 mechanism **I**; ADR-043).

Some tables hold platform rows and tenant rows under row-level security (dual-scope tables,
e.g. the audit log). Without a tenant context only the platform rows are visible, and RLS is
never bypassed, so jobs that must cover every row (IP retention, data-subject erasure, key
rotation, index rebuild) run in every scope:

* first without a tenant context (platform rows);
* then in one ``tenant_atomic`` per tenant registered, deleted tenants included (their audit
  rows still fall under the retention rules). Each tenant is a separate transaction, and a
  failure in one tenant is logged and counted without stopping the others.

It always runs inside ``platform_scope`` for a catalogued operation with mechanism I, as the
system actor, so start and end (with the tenant count) are in the platform audit log.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import structlog
from django.db import transaction

from apps.core.tenancy import tenant_atomic
from apps.core.tenancy.platform import SYSTEM, platform_scope
from apps.tenancy.models import Tenant

logger = structlog.get_logger("erp.tenancy")


@dataclass
class ScopeTotals:
    platform: int = 0
    tenants: int = 0
    tenant_rows: int = 0
    failed: int = 0

    @property
    def rows(self) -> int:
        return self.platform + self.tenant_rows


def in_every_scope(fn: Callable[[], int], *, operation: str, reason: str) -> ScopeTotals:
    totals = ScopeTotals()
    with platform_scope(operation=operation, actor=SYSTEM, reason=reason):
        with transaction.atomic():
            totals.platform = fn()
        for tenant in [t.as_context() for t in Tenant.objects.order_by("id")]:
            totals.tenants += 1
            try:
                with tenant_atomic(tenant):
                    totals.tenant_rows += fn()
            except Exception:
                totals.failed += 1
                logger.exception(
                    "tenancy.scope_iteration_failed", operation=operation, tenant_id=str(tenant.id)
                )
    return totals
