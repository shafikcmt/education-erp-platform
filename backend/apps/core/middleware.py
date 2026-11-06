"""Request ID middleware: correlation ID for logs, errors and responses."""

import re
import time
from collections.abc import Callable

import structlog
from django.http import HttpRequest, HttpResponse

from apps.core.ids import new_id

REQUEST_ID_HEADER = "X-Request-ID"
_META_KEY = "HTTP_X_REQUEST_ID"
# Accept upstream IDs (e.g. from Nginx) only when they are short and safe to log.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,128}$")

logger = structlog.get_logger("erp.request")


def get_request_id(request: HttpRequest) -> str:
    """Return the request ID assigned by :class:`RequestIDMiddleware` (or ``""``)."""
    return str(getattr(request, "request_id", ""))


class RequestIDMiddleware:
    """Assign/propagate ``X-Request-ID``, bind it to structlog context, log one line per request."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.META.get(_META_KEY, "")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else str(new_id())
        request.request_id = request_id  # type: ignore[attr-defined]

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        try:
            response = self.get_response(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
        response[REQUEST_ID_HEADER] = request_id
        if request.path not in ("/healthz", "/readyz"):
            logger.info(
                "http_request",
                request_id=request_id,
                method=request.method,
                path=request.path,
                status=response.status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
        return response


class ApiNoStoreMiddleware:
    """API responses are per-user and may carry one-time secrets: never cache them.

    Sets ``Cache-Control: no-store`` (and ``Pragma: no-cache``) on ``/api/`` responses that
    don't set their own policy (Phase 2 plan §6.6).
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if request.path.startswith("/api/") and not response.has_header("Cache-Control"):
            response["Cache-Control"] = "no-store"
            response["Pragma"] = "no-cache"
        return response
