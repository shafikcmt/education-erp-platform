"""RFC 9457 Problem Details error responses (docs/API_STANDARDS.md §4).

Every API error has a stable machine-readable ``code`` and the ``request_id``. Stack traces,
SQL and internal details are never returned to clients.
"""

from typing import Any

import structlog
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404, HttpRequest, JsonResponse
from rest_framework import exceptions as drf_exceptions
from rest_framework import status
from rest_framework.response import Response

from apps.core.middleware import get_request_id

PROBLEM_CONTENT_TYPE = "application/problem+json"
ERROR_TYPE_BASE = "https://docs.education-erp.invalid/errors/"

logger = structlog.get_logger("erp.errors")

_CODE_BY_EXCEPTION: list[tuple[type[Exception], str, str]] = [
    (drf_exceptions.ValidationError, "validation_error", "Validation failed"),
    (drf_exceptions.ParseError, "parse_error", "Malformed request"),
    (drf_exceptions.NotAuthenticated, "not_authenticated", "Authentication required"),
    (drf_exceptions.AuthenticationFailed, "authentication_failed", "Authentication failed"),
    (drf_exceptions.PermissionDenied, "permission_denied", "Permission denied"),
    (drf_exceptions.NotFound, "not_found", "Not found"),
    (drf_exceptions.MethodNotAllowed, "method_not_allowed", "Method not allowed"),
    (drf_exceptions.NotAcceptable, "not_acceptable", "Not acceptable"),
    (drf_exceptions.UnsupportedMediaType, "unsupported_media_type", "Unsupported media type"),
    (drf_exceptions.Throttled, "rate_limited", "Too many requests"),
]


class ProblemError(drf_exceptions.APIException):
    """API error with a stable Problem Details ``code`` (docs/API_STANDARDS.md §4).

    Subclasses set ``status_code``, ``problem_code``, ``title`` and ``default_detail``.
    ``extra`` adds documented, non-sensitive fields to the body (e.g. ``retry_after``).
    """

    status_code: int = status.HTTP_400_BAD_REQUEST
    problem_code = "error"
    title = "Request failed"
    default_detail = "The request could not be completed."

    def __init__(self, detail: str | None = None, *, extra: dict[str, Any] | None = None) -> None:
        super().__init__(detail)
        self.extra = extra or {}


def problem(
    *,
    status_code: int,
    code: str,
    title: str,
    detail: str,
    request_id: str,
    errors: list[dict[str, str]] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a Problem Details body."""
    body: dict[str, Any] = {
        "type": f"{ERROR_TYPE_BASE}{code}",
        "title": title,
        "status": status_code,
        "code": code,
        "detail": detail,
        "request_id": request_id,
    }
    if errors:
        body["errors"] = errors
    if extra:
        body.update(extra)
    return body


def _flatten_validation_errors(data: Any, prefix: str = "") -> list[dict[str, str]]:
    """Convert DRF's nested error structure into ``[{field, code, message}]``."""
    items: list[dict[str, str]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            field = f"{prefix}.{key}" if prefix else str(key)
            items.extend(_flatten_validation_errors(value, field))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            if isinstance(value, dict | list):
                items.extend(_flatten_validation_errors(value, f"{prefix}[{index}]"))
            else:
                items.extend(_flatten_validation_errors(value, prefix))
    else:
        code = getattr(data, "code", "invalid")
        items.append(
            {"field": prefix or "non_field_errors", "code": str(code), "message": str(data)}
        )
    return items


def problem_details_exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    """DRF ``EXCEPTION_HANDLER`` returning Problem Details for every error (incl. 500s)."""
    request = context.get("request")
    request_id = get_request_id(request) if request is not None else ""

    if isinstance(exc, Http404):
        exc = drf_exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = drf_exceptions.PermissionDenied()

    if isinstance(exc, drf_exceptions.APIException):
        code, title = "error", "Request failed"
        if isinstance(exc, ProblemError):
            code, title = exc.problem_code, exc.title
        else:
            for exc_type, mapped_code, mapped_title in _CODE_BY_EXCEPTION:
                if isinstance(exc, exc_type):
                    code, title = mapped_code, mapped_title
                    break
        errors = None
        if isinstance(exc, drf_exceptions.ValidationError):
            errors = _flatten_validation_errors(exc.detail)
            detail = "One or more fields are invalid."
        else:
            detail = str(exc.detail) if not isinstance(exc.detail, dict | list) else title
        body = problem(
            status_code=exc.status_code,
            code=code,
            title=title,
            detail=detail,
            request_id=request_id,
            errors=errors,
            extra=exc.extra if isinstance(exc, ProblemError) else None,
        )
        headers: dict[str, str] = {}
        if getattr(exc, "auth_header", None):
            headers["WWW-Authenticate"] = str(exc.auth_header)  # type: ignore[attr-defined]
        if getattr(exc, "wait", None):
            headers["Retry-After"] = str(int(exc.wait))  # type: ignore[attr-defined]
        return Response(
            body, status=exc.status_code, headers=headers, content_type=PROBLEM_CONTENT_TYPE
        )

    logger.exception("unhandled_api_exception", exc_type=type(exc).__name__)
    if request is not None:
        # For middleware that must react to the cause after the response is built (the
        # tenant request path audits isolation violations). Never sent to the client.
        getattr(request, "_request", request).unhandled_exception = exc
    body = problem(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="internal_error",
        title="Internal server error",
        detail="An unexpected error occurred.",
        request_id=request_id,
    )
    return Response(
        body, status=status.HTTP_500_INTERNAL_SERVER_ERROR, content_type=PROBLEM_CONTENT_TYPE
    )


def _json_problem(request: HttpRequest, status_code: int, code: str, title: str) -> JsonResponse:
    body = problem(
        status_code=status_code,
        code=code,
        title=title,
        detail=title,
        request_id=get_request_id(request),
    )
    return JsonResponse(body, status=status_code, content_type=PROBLEM_CONTENT_TYPE)


def problem_response(
    request: HttpRequest, status_code: int, code: str, title: str, detail: str = ""
) -> JsonResponse:
    """Problem Details response for middleware (outside DRF's exception handling)."""
    body = problem(
        status_code=status_code,
        code=code,
        title=title,
        detail=detail or title,
        request_id=get_request_id(request),
    )
    return JsonResponse(body, status=status_code, content_type=PROBLEM_CONTENT_TYPE)


def uniform_not_found(request: HttpRequest) -> JsonResponse:
    """The single 404 body for unknown paths, rejected hosts and unknown tenants alike."""
    return _json_problem(request, 404, "not_found", "Not found")


def handler404(request: HttpRequest, exception: Exception | None = None) -> JsonResponse:
    """Django-level 404 (non-DRF routes) as Problem Details."""
    return _json_problem(request, 404, "not_found", "Not found")


def api_not_found(request: HttpRequest) -> JsonResponse:
    """Catch-all for unknown ``/api/`` paths (independent of ``DEBUG``)."""
    return _json_problem(request, 404, "not_found", "Not found")


def handler500(request: HttpRequest) -> JsonResponse:
    """Django-level 500 (non-DRF routes) as Problem Details, without internals."""
    return _json_problem(request, 500, "internal_error", "Internal server error")
