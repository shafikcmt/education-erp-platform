"""Core Celery tasks."""

from celery import shared_task


@shared_task(name="core.ping")
def ping() -> str:
    """Round-trip check for the broker/worker/result backend (no tenant data)."""
    return "pong"
