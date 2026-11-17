"""Who may use a tenant host (Phase 3 plan §8.2, §10.5, §12.4; decisions D2, D7).

Both checks run inside the tenant request transaction, on every request, without a cache, so a
suspension or a removed membership is effective on the very next request.

M3 scope (fail closed until later milestones add the missing pieces):

* a **suspended** tenant denies every signed-in request, owners included; the restricted
  owner mode of D2 arrives with M5;
* an **offboarding** tenant accepts no writes;
* support sessions are not recognised yet (M5), so platform staff without a membership are
  treated like any other non-member.
"""

from __future__ import annotations

import uuid

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse

from apps.audit.services import record as audit
from apps.core.exceptions import problem_response
from apps.core.tenancy import TenantContext
from apps.tenancy.models import Membership
from apps.tenancy.rules import TenantStatus

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# code -> (title, detail). Stable Problem Details codes (plan §12.4).
_DENIALS: dict[str, tuple[str, str]] = {
    "tenant_suspended": ("Institution suspended", "This institution is currently suspended."),
    "not_a_member": ("Not a member", "You are not a member of this institution."),
    "membership_inactive": ("Membership inactive", "Your membership is not active."),
    "tenant_unavailable": (
        "Institution unavailable",
        "This institution is being closed and no longer accepts changes.",
    ),
}


def membership_status(user_id: uuid.UUID | None) -> str | None:
    """The current tenant's membership status of ``user_id`` (``None``: no membership)."""
    if user_id is None:
        return None
    status: str | None = (
        Membership.objects.filter(user_id=user_id).values_list("status", flat=True).first()
    )
    return status


def _denial_reason(request: HttpRequest, tenant: TenantContext) -> str | None:
    if tenant.status == TenantStatus.SUSPENDED:
        return "tenant_suspended"
    status = membership_status(request.user.pk)
    if status is None:
        return "not_a_member"
    if status != Membership.Status.ACTIVE:
        return "membership_inactive"
    if tenant.status != TenantStatus.ACTIVE and request.method not in _SAFE_METHODS:
        return "tenant_unavailable"
    return None


def check_request(request: HttpRequest, tenant: TenantContext) -> HttpResponse | None:
    """``None`` to continue, or the 403 response. Anonymous requests are left to the view."""
    if not request.user.is_authenticated:
        return None
    reason = _denial_reason(request, tenant)
    if reason is None:
        return None
    # Durable (survives the rollback of this request) and bounded like ``authz.denied`` in
    # the permission classes: one event per user, tenant and reason per minute.
    if cache.add(f"t:{tenant.id}:authz:denied:{request.user.pk}:{reason}", 1, timeout=60):
        audit(
            "authz.denied",
            actor=request.user,
            request=request,
            outcome="denied",
            metadata={"permission": "", "reason": reason},
        )
    title, detail = _DENIALS[reason]
    return problem_response(request, 403, reason, title, detail)


def sign_in_guard(request: HttpRequest, user: object) -> str | None:
    """``IDENTITY_SIGN_IN_GUARDS`` hook. On a tenant host a correct password is not enough:
    the tenant must be usable and the user an active member. The caller answers every
    refusal with the same generic invalid-credentials error (D7); the reason returned here
    is only for the audit log."""
    tenant: TenantContext | None = getattr(request, "tenant", None)
    if tenant is None:
        return None
    if tenant.status == TenantStatus.SUSPENDED:
        return "tenant_suspended"
    status = membership_status(getattr(user, "pk", None))
    if status is None:
        return "not_a_member"
    if status != Membership.Status.ACTIVE:
        return "membership_inactive"
    return None
