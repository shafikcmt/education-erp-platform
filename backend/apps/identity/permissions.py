"""DRF permission building blocks tied to session security state (plan §6.1, §6.6).

* **MFA gate:** a privileged account (ADR-035) whose session has not completed MFA can use only
  views marked ``allow_during_mfa_enrollment = True`` (MFA setup, step-up, ``/me/``, logout)
  until it enrolls; once enrolled, an unverified session is refused (``mfa_required``).
* **Step-up:** :class:`RequireStepUp` demands a password re-entry within the last 10 minutes.
"""

from typing import Any

from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from apps.identity import errors
from apps.identity import session_state as state


def enforce_mfa_gate(request: Request, view: Any) -> None:
    user = request.user
    if state.mfa_verified(request):
        return
    from apps.identity.services.mfa import has_mfa
    from apps.rbac.engine import PLATFORM, user_requires_mfa

    # Phase 3: on a tenant host, privileged tenant roles count too (same rule as at sign-in).
    target = getattr(request, "scope_target", PLATFORM)
    if not user_requires_mfa(user, target=target):  # type: ignore[arg-type]
        return
    if has_mfa(user):  # type: ignore[arg-type]
        raise errors.MfaRequired()
    if getattr(view, "allow_during_mfa_enrollment", False):
        return
    raise errors.MfaEnrollmentRequired()


class IsAuthenticatedSession(BasePermission):
    """Authenticated + MFA gate, with no permission code: only for views on the reviewed
    session-only allow-list (logout, step-up). Every other view uses ``HasPermission``."""

    def has_permission(self, request: Request, view: Any) -> bool:
        if not (request.user and request.user.is_authenticated):
            raise NotAuthenticated()
        enforce_mfa_gate(request, view)
        return True


class RequireStepUp(BasePermission):
    """Fresh step-up (password + MFA within 10 minutes) for this view's unsafe methods."""

    def has_permission(self, request: Request, view: Any) -> bool:
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        if not state.step_up_fresh(request):
            raise errors.StepUpRequired()
        return True
