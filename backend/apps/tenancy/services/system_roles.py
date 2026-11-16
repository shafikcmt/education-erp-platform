"""Platform operation P7: keep every tenant's system role copies equal to the templates
(Phase 3 M4; plan §6.3; owner decision Q5).

Mechanism **I** (per-tenant iteration): one tenant transaction per tenant, each failure
isolated, so a problem in one tenant never blocks or affects another. Idempotent. Runs in the
deployment bootstrap right after ``seed_roles`` (``manage.py sync_tenant_roles``).
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from apps.audit.models import ActorType
from apps.audit.services import record
from apps.core.tenancy import tenant_atomic
from apps.core.tenancy.platform import SYSTEM, platform_scope
from apps.rbac.tenant_roles import sync_system_copies
from apps.tenancy.models import Tenant
from apps.tenancy.rules import TenantStatus

logger = structlog.get_logger("erp.tenancy")


@dataclass
class SyncSummary:
    tenants: int = 0
    changed: int = 0
    failed: int = 0


def sync_all_tenants() -> SyncSummary:
    summary = SyncSummary()
    with platform_scope(operation="P7", actor=SYSTEM, reason="sync tenant system role copies"):
        tenants = [t.as_context() for t in Tenant.objects.exclude(status=TenantStatus.DELETED)]
        for tenant in tenants:
            summary.tenants += 1
            try:
                with tenant_atomic(tenant):
                    if sync_system_copies(tenant.id).changed:
                        summary.changed += 1
            except Exception:
                summary.failed += 1
                logger.exception("tenancy.system_roles.sync_failed", tenant_id=str(tenant.id))
    record(
        "rbac.tenant_roles.synced",
        actor_type=ActorType.SYSTEM,
        outcome="success" if not summary.failed else "failure",
        metadata={
            "tenants": summary.tenants,
            "changed": summary.changed,
            "failed": summary.failed,
        },
    )
    return summary
