"""Audit housekeeping (platform task: no tenant data is read)."""

from celery import shared_task

from apps.audit.services import anonymize_expired_ips as _anonymize


@shared_task(name="audit.anonymize_expired_ips")
def anonymize_expired_ips() -> int:
    """Daily ADR-036 retention job."""
    return _anonymize()
