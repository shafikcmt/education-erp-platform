"""Sentry initialisation (enabled only when ``SENTRY_DSN`` is configured).

Secrets must never reach error tracking (Phase 2 plan §6.6, §6.8):

* ``send_default_pii=False`` (no cookies, headers with credentials, user IPs);
* ``include_local_variables=False`` (a password or TOTP secret in a stack frame stays local);
* :func:`scrub_event` drops request bodies and redacts sensitive keys everywhere else, and drops
  MFA/auth payloads entirely.
"""

from typing import Any

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration

from apps.core.logging import REDACTED, _is_sensitive

# Requests to these paths may carry credentials; their bodies and query strings are dropped.
_SENSITIVE_PATH_MARKERS = ("/auth/", "/me/", "/platform/")


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: (REDACTED if _is_sensitive(str(k)) else _scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def scrub_event(event: dict[str, Any], hint: dict[str, Any] | None = None) -> dict[str, Any]:
    """Sentry ``before_send`` hook: remove request bodies, cookies and sensitive keys."""
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)  # request bodies are never sent
        request.pop("cookies", None)
        url = str(request.get("url", ""))
        if any(marker in url for marker in _SENSITIVE_PATH_MARKERS):
            request.pop("query_string", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                k: v
                for k, v in headers.items()
                if k.lower() not in {"cookie", "authorization", "x-csrftoken"}
            }
    for key in ("extra", "contexts", "tags"):
        if key in event:
            event[key] = _scrub(event[key])
    breadcrumbs = event.get("breadcrumbs")
    if isinstance(breadcrumbs, dict) and isinstance(breadcrumbs.get("values"), list):
        for crumb in breadcrumbs["values"]:
            if isinstance(crumb, dict) and "data" in crumb:
                crumb["data"] = _scrub(crumb["data"])
    return event


def init_sentry(*, dsn: str, environment: str, release: str, traces_sample_rate: float) -> None:
    """Initialise Sentry with PII disabled; personal data must never reach error tracking."""
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        traces_sample_rate=traces_sample_rate,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        before_send=scrub_event,  # type: ignore[arg-type]
        integrations=[DjangoIntegration(), CeleryIntegration()],
    )
