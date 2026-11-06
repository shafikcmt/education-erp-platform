"""Identity Celery tasks. All are **platform tasks**: they touch no tenant data (plan §4.6)."""

from celery import shared_task

from apps.identity.services import notifications


@shared_task(name="identity.deliver_security_email", queue="notifications")
def deliver_security_email(sealed_hex: str) -> None:
    """Open the sealed payload, render the en/bn templates and send (never logs content)."""
    notifications.deliver(sealed_hex)


@shared_task(name="identity.housekeeping")
def housekeeping() -> dict[str, int]:
    """Daily: anonymise expired session IPs (ADR-036) and purge expired, unused tokens."""
    from apps.identity.services.maintenance import run_housekeeping

    return run_housekeeping()
