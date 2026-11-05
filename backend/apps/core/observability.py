"""Sentry initialisation (enabled only when ``SENTRY_DSN`` is configured)."""

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration


def init_sentry(*, dsn: str, environment: str, release: str, traces_sample_rate: float) -> None:
    """Initialise Sentry with PII disabled; personal data must never reach error tracking."""
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        traces_sample_rate=traces_sample_rate,
        send_default_pii=False,
        integrations=[DjangoIntegration(), CeleryIntegration()],
    )
