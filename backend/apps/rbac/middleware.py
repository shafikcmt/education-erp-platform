"""Attach the authorization scope to every request (plan §4.3).

Phase 2 serves only the platform host, so every request targets ``PLATFORM``. Phase 3 resolves
the tenant host here and sets the tenant/institution/campus target; views don't change.
"""

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from apps.rbac.engine import PLATFORM


class ScopeTargetMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.scope_target = PLATFORM  # type: ignore[attr-defined]
        return self.get_response(request)
