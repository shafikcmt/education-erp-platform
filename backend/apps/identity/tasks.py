"""Identity Celery tasks. All are **platform tasks**: they touch no tenant data (plan §4.6)."""

from apps.core.tasking import platform_task
from apps.identity.services import notifications


@platform_task(name="identity.deliver_security_email", operation="P12")
def deliver_security_email(sealed_hex: str) -> None:
    """Open the sealed payload, render the en/bn templates and send (never logs content)."""
    notifications.deliver(sealed_hex)


@platform_task(name="identity.housekeeping", operation="P12")
def housekeeping() -> dict[str, int]:
    """Daily: anonymise expired session IPs (ADR-036) and purge expired, unused tokens."""
    from apps.identity.services.maintenance import run_housekeeping

    return run_housekeeping()
