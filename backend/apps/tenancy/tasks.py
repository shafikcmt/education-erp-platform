"""Scheduled and per-tenant tasks of the tenancy layer (Phase 3 M6-M7).

* ``audit.anonymize_expired_ips`` — platform operation **P10**: ADR-036 IP retention for the
  platform log and every tenant's log (mechanism I, ``apps.tenancy.iteration``). It lives here
  because covering tenants needs the registry and ``audit`` sits below ``tenancy``.
* ``tenancy.sweep_support_sessions`` — platform task (P12 housekeeping, registry read only)
  that fans out one ``tenancy.expire_support_sessions`` tenant task per tenant (mechanism I).
* ``tenancy.expire_support_sessions`` — tenant task: marks the tenant's lapsed support
  sessions ``expired`` and ends the staff sign-ins on its hosts. Runs for active and suspended
  tenants (a suspended tenant's sessions still have to end).
"""

from __future__ import annotations

import uuid

from django.utils import timezone

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
