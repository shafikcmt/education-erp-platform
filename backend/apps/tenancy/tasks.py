"""Scheduled and per-tenant tasks of the tenancy layer (Phase 3 M6-M7).

* ``audit.anonymize_expired_ips`` — platform operation **P10**: ADR-036 IP retention for the
  platform log and every tenant's log (mechanism I, ``apps.tenancy.iteration``). It lives here
  because covering tenants needs the registry and ``audit`` sits below ``tenancy``.
* ``tenancy.sweep_support_sessions`` — platform task (P12 housekeeping, registry read only)
  that fans out one ``tenancy.expire_support_sessions`` tenant task per tenant (mechanism I).
* ``tenancy.report_isolation_denials`` — platform task **P14** (registry/platform log read
  only): a daily summary of blocked isolation violations (``tenancy.isolation.blocked`` platform
  events, tenant id as metadata) per tenant and reason, as one structured log line. No tenant
  data is read (plan §14 "security monitoring").
* ``tenancy.expire_support_sessions`` — tenant task: marks the tenant's lapsed support
  sessions ``expired`` and ends the staff sign-ins on its hosts. Runs for active and suspended
  tenants (a suspended tenant's sessions still have to end).
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import timedelta
from typing import Any

import structlog
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import anonymize_expired_ips as _anonymize
from apps.core.tasking import platform_task
from apps.tenancy.iteration import in_every_scope
from apps.tenancy.models import SupportSession, Tenant
from apps.tenancy.rules import TenantStatus
from apps.tenancy.tasking import tenant_task


@platform_task(name="audit.anonymize_expired_ips", operation="P10")
def anonymize_expired_ips() -> int:
    """Daily ADR-036 retention job (P10)."""
    totals = in_every_scope(
        _anonymize, operation="P10", reason="anonymise expired security-event IPs"
    )
    return totals.rows


logger = structlog.get_logger("erp.tenancy")


@platform_task(name="tenancy.report_isolation_denials", operation="P14")
def report_isolation_denials(hours: int = 24) -> dict[str, Any]:
    """Count the platform log's ``tenancy.isolation.blocked`` events of the last ``hours`` per
    tenant and reason (P14). Logged at warning level when anything was blocked."""
    since = timezone.now() - timedelta(hours=hours)
    by_tenant: Counter[str] = Counter()
    by_reason: Counter[str] = Counter()
    for metadata in AuditEvent.objects.filter(
        tenant_id__isnull=True, action="tenancy.isolation.blocked", occurred_at__gte=since
    ).values_list("metadata", flat=True):
        data = metadata if isinstance(metadata, dict) else {}
        by_tenant[str(data.get("tenant_id") or "platform")] += 1
        by_reason[str(data.get("reason") or "unknown")] += 1
    total = sum(by_tenant.values())
    report = {
        "hours": hours,
        "total": total,
        "by_tenant": dict(by_tenant.most_common(50)),
        "by_reason": dict(by_reason),
    }
    (logger.warning if total else logger.info)("tenancy.isolation.daily_report", **report)
    return report


@platform_task(name="tenancy.sweep_support_sessions", operation="P12")
def sweep_support_sessions() -> int:
    """Enqueue one expiry task per tenant that may hold open support sessions."""
    tenant_ids = list(
        Tenant.objects.filter(
            status__in=(TenantStatus.ACTIVE, TenantStatus.SUSPENDED, TenantStatus.OFFBOARDING)
        ).values_list("id", flat=True)
    )
    for tenant_id in tenant_ids:
        expire_support_sessions.delay(tenant_id=str(tenant_id))
    return len(tenant_ids)


@tenant_task(
    name="tenancy.expire_support_sessions",
    statuses=(TenantStatus.ACTIVE, TenantStatus.SUSPENDED, TenantStatus.OFFBOARDING),
)
def expire_support_sessions(*, tenant_id: uuid.UUID) -> int:
    from apps.tenancy.services.support import expire_session

    lapsed = list(
        SupportSession.objects.filter(
            status__in=SupportSession.OPEN_STATUSES, ends_at__lte=timezone.now()
        ).values_list("id", flat=True)
    )
    for session_id in lapsed:
        expire_session(session_id)
    return len(lapsed)
