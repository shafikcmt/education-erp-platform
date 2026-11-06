"""Shared API helpers: CSRF for anonymous endpoints, service-error translation, ID lookup."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Model, QuerySet
from rest_framework import exceptions, serializers
from rest_framework.permissions import SAFE_METHODS
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.identity import errors
from apps.identity.authentication import SessionAuthentication

_FORBIDDEN_GUARD_RAILS = {"privilege_escalation", "insufficient_privilege"}


class CsrfProtectedView(APIView):
    """Enforce CSRF on unsafe methods for anonymous callers too (login CSRF; DRF only checks
    authenticated sessions)."""

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        if request.method not in SAFE_METHODS:
            SessionAuthentication().enforce_csrf(request)


@contextmanager
def service_errors() -> Iterator[None]:
    """Translate Django ``ValidationError`` and RBAC guard-rail violations into API errors."""
    from apps.rbac.services import GuardRailViolation

    try:
        yield
    except GuardRailViolation as exc:
        err = errors.GuardRail(exc.code, str(exc))
        if exc.code in _FORBIDDEN_GUARD_RAILS:
            err.status_code = 403
        raise err from exc
    except DjangoValidationError as exc:
        detail = (
            exc.message_dict if hasattr(exc, "error_dict") else {"non_field_errors": exc.messages}
        )
        raise serializers.ValidationError(detail) from exc


def get_or_404[M: Model](queryset: QuerySet[M], pk: Any) -> M:
    """Lookup by UUID; malformed IDs and missing rows are both 404 (no existence disclosure)."""
    try:
        key = uuid.UUID(str(pk))
    except ValueError:
        raise exceptions.NotFound() from None
    obj = queryset.filter(pk=key).first()
    if obj is None:
        raise exceptions.NotFound()
    return obj
