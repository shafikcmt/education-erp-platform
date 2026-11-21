"""Module entitlement enforcement for API views (Phase 4 M4; ADR-052, ADR-054 Q3).

``ModuleEntitled("<code>")`` is a DRF permission class evaluated **before** the permission
check. On a tenant request for a module the tenant is not entitled to, it raises
``403 module_not_entitled``; data is never deleted. It never decides on its own:

* platform-host requests (no tenant) are left to the view's other classes;
* anonymous callers are left to the next class (``401``), so entitlements don't leak;
* platform modules (``core``, ``tenancy``, ``identity``, ``rbac``, ``audit`` …) are always
  entitled and need no lookup.

:class:`ModuleGatedView` adds the class from the view's required ``module_code``; the URL
audit checks that every view reachable on a tenant host declares one.
"""

from __future__ import annotations

from functools import cache as memoize
from typing import Any

from django.core.cache import cache
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from apps.audit.services import record as audit
from apps.module_registry.entitlements import is_entitled
from apps.module_registry.errors import ModuleNotEntitledError
from apps.module_registry.registry import declared_modules


@memoize
def _platform_modules() -> frozenset[str]:
    return frozenset(
        code for code, spec in declared_modules().items() if spec.category == "platform"
    )


class ModuleCheck(BasePermission):
    """Base class (the URL audit looks for it on views of non-platform modules)."""

    module_code = ""

    def has_permission(self, request: Request, view: Any) -> bool:
        code = self.module_code
        if not code:
            return False  # fail closed: a gated view without a module
        if code in _platform_modules():
            return True
        if getattr(request, "tenant", None) is None:
            return True  # platform host: the view's own classes decide
        user = request.user
        if not (user and user.is_authenticated):
            return True  # the permission class answers 401 without revealing entitlements
        if is_entitled(code):
            return True
        if cache.add(f"authz:module:{user.pk}:{code}", 1, timeout=60):
            audit(
                "authz.denied",
                actor=user,
                request=request,
                outcome="denied",
                metadata={"module": code, "reason": "module_not_entitled"},
            )
        raise ModuleNotEntitledError()


def ModuleEntitled(code: str) -> type[ModuleCheck]:  # noqa: N802 - reads like a class
    if code not in declared_modules():
        raise ValueError(f"Unknown module code {code!r}.")
    return type(f"ModuleEntitled_{code}", (ModuleCheck,), {"module_code": code})


# Mixin for API views: ``module_code`` is required; the entitlement check runs first. No
# docstring on purpose: drf-spectacular would publish it as the description of every operation.
class ModuleGatedView:
    module_code = ""

    def get_permissions(self) -> list[Any]:
        permissions: list[Any] = super().get_permissions()  # type: ignore[misc]
        return [ModuleEntitled(self.module_code)(), *permissions]
