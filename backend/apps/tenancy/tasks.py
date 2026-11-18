"""Scheduled platform tasks of the tenancy layer (Phase 3 M6).

``audit.anonymize_expired_ips`` is platform operation **P10**: ADR-036 IP retention for the
platform log and for every tenant's log (mechanism I). It moved here from ``apps.audit``
because covering the tenant rows needs the tenant registry, and ``audit`` sits below
``tenancy`` in the import graph. The task name and the beat schedule are unchanged.
"""

from celery import shared_task

from apps.audit.services import anonymize_expired_ips as _anonymize
from apps.tenancy.iteration import in_every_scope


@shared_task(name="audit.anonymize_expired_ips")
def anonymize_expired_ips() -> int:
    """Daily ADR-036 retention job (P10)."""
    totals = in_every_scope(
        _anonymize, operation="P10", reason="anonymise expired security-event IPs"
    )
    return totals.rows
