"""Structured logging configuration (structlog + stdlib).

* ``json`` format for staging/production (one JSON object per line on stdout).
* ``console`` format for local development.
* Every event carries the request context bound by ``RequestIDMiddleware`` (``request_id``;
  ``tenant_id``/``user_id`` are added in later phases).
* Sensitive keys are redacted before rendering — never log secrets or PII.
"""

from collections.abc import MutableMapping
from typing import Any

import structlog

REDACTED = "[REDACTED]"
SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "cookie",
        "set-cookie",
        "sessionid",
        "csrftoken",
        "api_key",
        "apikey",
        "otp",
        "mfa_code",
        "national_id",
    }
)


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return lowered in SENSITIVE_KEYS or any(
        marker in lowered for marker in ("password", "secret", "token")
    )


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: (REDACTED if _is_sensitive(str(k)) else _redact(v)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(_redact(v) for v in value)
    return value


def redact_sensitive(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor: replace values of sensitive keys (recursively) with a marker."""
    for key in list(event_dict.keys()):
        if _is_sensitive(key):
            event_dict[key] = REDACTED
        else:
            event_dict[key] = _redact(event_dict[key])
    return event_dict


_SHARED_PROCESSORS: list[Any] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    redact_sensitive,
]


def build_logging_config(*, level: str, fmt: str) -> dict[str, Any]:
    """Configure structlog and return a ``LOGGING`` dict for Django."""
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if fmt == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            *_SHARED_PROCESSORS,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "structured": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": [
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.format_exc_info,
                    renderer,
                ],
                "foreign_pre_chain": _SHARED_PROCESSORS,
            }
        },
        "handlers": {"stdout": {"class": "logging.StreamHandler", "formatter": "structured"}},
        "root": {"handlers": ["stdout"], "level": level},
        "loggers": {
            "django.server": {"level": "WARNING"},  # request logging is done by our middleware
            "django.db.backends": {"level": "WARNING"},
        },
    }
