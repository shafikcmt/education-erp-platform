"""DRF permission classes enforcing ``has_perm`` on every protected view (plan §4.4, §8).

``HasPermission("identity.user.view")`` or ``HasPermission({"GET": "...", "POST": "..."})``
returns a permission class. Methods missing from the mapping are denied. After the permission
check, the permission's flags apply: ``requires_mfa`` needs an MFA-verified session and
``requires_step_up`` a fresh step-up. Scope comes from ``request.scope_target`` (Phase 3 sets
tenant targets in middleware; views don't change). Denials are audited, aggregated to at most
one row per actor + permission per minute.
"""

from typing import Any

from django.core.cache import cache
from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from apps.audit.services import record as audit
from apps.identity import errors
from apps.identity import session_state as state
from apps.identity.permissions import enforce_mfa_gate
from apps.rbac.engine import PLATFORM, has_perm, permission_info

_SAFE_ALIASES = {"HEAD": "GET", "OPTIONS": "GET"}


class PermissionCheck(BasePermission):
    """Base class (the URL audit test looks for subclasses of it on every protected view)."""

    codes: dict[str, str] = {}

    @classmethod
    def code_for(cls, method: str) -> str | None:
        method = method.upper()
        return cls.codes.get(method) or cls.codes.get(_SAFE_ALIASES.get(method, ""))

    def has_permission(self, request: Request, view: Any) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            raise NotAuthenticated()
        enforce_mfa_gate(request, view)
        code = self.code_for(request.method or "")
        if code is None:
            return False
        target = getattr(request, "scope_target", PLATFORM)
        if not has_perm(user, code, target=target):
            if cache.add(f"authz:denied:{user.pk}:{code}", 1, timeout=60):
                audit(
                    "authz.denied",
                    actor=user,
                    request=request,
                    outcome="denied",
                    metadata={"permission": code, "reason": "missing_permission"},
                )
            return False
        info = permission_info(code)
        if info.requires_mfa and not state.mfa_verified(request):
            raise errors.MfaRequired()
        if info.requires_step_up and not state.step_up_fresh(request):
            raise errors.StepUpRequired()
        return True


def HasPermission(codes: str | dict[str, str]) -> type[PermissionCheck]:  # noqa: N802
    mapping = (
        dict.fromkeys(("GET", "POST", "PUT", "PATCH", "DELETE"), codes)
        if isinstance(codes, str)
        else {k.upper(): v for k, v in codes.items()}
    )
    name = "HasPermission_" + "_".join(sorted(set(mapping.values()))).replace(".", "_")
    return type(name, (PermissionCheck,), {"codes": mapping})


class AnyPermissionCheck(PermissionCheck):
    """Allows the request when the actor holds **any** of ``any_of`` (flags of the granted code
    still apply). Used for read views shared by several roles."""

    any_of: tuple[str, ...] = ()

    @classmethod
    def code_for(cls, method: str) -> str | None:
        return cls.any_of[0] if cls.any_of else None

    def has_permission(self, request: Request, view: Any) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            raise NotAuthenticated()
        enforce_mfa_gate(request, view)
        target = getattr(request, "scope_target", PLATFORM)
        for code in self.any_of:
            if has_perm(user, code, target=target):
                info = permission_info(code)
                if info.requires_mfa and not state.mfa_verified(request):
                    raise errors.MfaRequired()
                if info.requires_step_up and not state.step_up_fresh(request):
                    raise errors.StepUpRequired()
                return True
        return False


def HasAnyPermission(*codes: str) -> type[AnyPermissionCheck]:  # noqa: N802
    if not codes:
        raise ValueError("HasAnyPermission needs at least one permission code")
    name = "HasAnyPermission_" + "_".join(sorted(codes)).replace(".", "_")
    return type(name, (AnyPermissionCheck,), {"any_of": tuple(codes)})
