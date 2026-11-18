"""Core Celery tasks."""

from apps.core.tasking import platform_task


@platform_task(name="core.ping", operation="P12")
def ping() -> str:
    """Round-trip check for the broker/worker/result backend (no tenant data)."""
    return "pong"
