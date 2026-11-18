"""Who may use a tenant host (Phase 3 plan §8.2, §10.5, §11, §12.4; decisions D2, D7).

Both checks run inside the tenant request transaction, on every request, without a cache, so a
suspension, a removed membership or a revoked support session is effective on the very next
request.

* **Members** need an active membership. While the tenant is ``offboarding`` nobody writes.
* **Suspended tenants (D2, restricted mode):** only active tenant owners get in, and only to
  views that declare ``suspended_tenant_allowed`` (support-session review and sign-out); every
  other request gets ``tenant_suspended``. Support sessions can't be used (S10).
* **Platform staff without a membership** get in only with a usable support session of THIS
  tenant (looked up under RLS, S2). Support access is read-only (S3): an unsafe method gets
  ``support_access_read_only``. A lapsed, revoked or ended session gets
  ``support_session_expired``. Denials leave durable evidence.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from apps.audit.models import ActorType
from apps.audit.services import record as audit
from apps.core.exceptions import problem_response
from apps.core.tenancy import TenantContext
from apps.core.tenancy.keys import tenant_cache_key
from apps.rbac.models import RoleAssignment
from apps.rbac.role_templates import TENANT_OWNER
from apps.tenancy import support
from apps.tenancy.models import Membership, SupportSession
from apps.tenancy.rbac_sources import live_assignments
from apps.tenancy.rules import TenantStatus

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# code -> (title, detail). Stable Problem Details codes (plan §12.4).
_DENIALS: dict[str, tuple[str, str]] = {
    "tenant_suspended": ("Institution suspended", "This institution is currently suspended."),
    "not_a_member": ("Not a member", "You are not a member of this institution."),
    "membership_inactive": ("Membership inactive", "Your membership is not active."),
    "tenant_unavailable": (
        "Institution unavailable",
        "This institution is being closed and no longer accepts changes.",
    ),
    "support_access_read_only": (
        "Read-only support access",
        "Support access can only read data.",
    ),
    "support_session_expired": (
        "Support access ended",
        "The support session has ended, expired or been revoked.",
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


def is_active_owner(user_id: Any) -> bool:
    """An active member holding the tenant-scope ``tenant_owner`` system role right now."""
    return RoleAssignment.objects.filter(
        live_assignments(),
        membership__user_id=user_id,
        membership__status=Membership.Status.ACTIVE,
        scope_type="tenant",
        role__is_system=True,
        role__template__code=TENANT_OWNER,
    ).exists()


def _deny(request: HttpRequest, tenant: TenantContext, reason: str) -> HttpResponse:
    # Durable (survives the rollback of this request) and bounded like ``authz.denied`` in
    # the permission classes: one event per user, tenant and reason per minute.
    support_reasons = {"support_access_read_only", "support_session_expired"}
    if cache.add(
        tenant_cache_key("authz", "denied", request.user.pk, reason, tenant=tenant), 1, timeout=60
    ):
        if reason == "support_access_read_only":
            session = getattr(request, "support_session", None)
            audit(
                "support.write_rejected",
                actor_user_id=request.user.pk,
                actor_type=ActorType.SUPPORT,
                request=request,
                outcome="denied",
                support_session_id=support.session_id(session),
                metadata={"method": request.method or ""},
            )
        elif reason in support_reasons:
            audit(
                "support.access_denied",
                actor_user_id=request.user.pk,
                actor_type=ActorType.SUPPORT,
                request=request,
                outcome="denied",
                metadata={"reason": reason},
            )
        else:
            audit(
                "authz.denied",
                actor_user_id=request.user.pk,
                request=request,
                outcome="denied",
                metadata={"permission": "", "reason": reason},
            )
    title, detail = _DENIALS[reason]
    return problem_response(request, 403, reason, title, detail)


def _expire_later(request: HttpRequest, session: SupportSession) -> None:
    """Mark a lapsed session ``expired`` and end the staff member's sessions on this tenant's
    hosts, in a transaction of its own (this request is rolled back)."""
    from apps.tenancy.services.support import expire_session

    followups: list[Callable[[], None]] = request.__dict__.setdefault("tenant_followups", [])
    followups.append(lambda: expire_session(session.pk))


def check_request(
    request: HttpRequest, tenant: TenantContext, view_class: Any = None
) -> HttpResponse | None:
    """``None`` to continue, or the 403 response. Anonymous requests are left to the view."""
    if not request.user.is_authenticated:
        return None
    user_id = request.user.pk
    status = membership_status(user_id)
    if tenant.status == TenantStatus.SUSPENDED:
        allowed = getattr(view_class, "suspended_tenant_allowed", False)
        if status == Membership.Status.ACTIVE and allowed and is_active_owner(user_id):
            return None  # restricted owner mode (D2)
        return _deny(request, tenant, "tenant_suspended")
    if status == Membership.Status.ACTIVE:
        if tenant.status != TenantStatus.ACTIVE and request.method not in SAFE_METHODS:
            return _deny(request, tenant, "tenant_unavailable")
        return None
    session = support.usable_session(user_id)
    if session is not None and tenant.status == TenantStatus.ACTIVE:
        request.support_session = session  # type: ignore[attr-defined]
        if request.method not in SAFE_METHODS:
            return _deny(request, tenant, "support_access_read_only")
        if session.status == SupportSession.Status.APPROVED:
            from apps.tenancy.services.support import mark_started

            mark_started(session, request=request)
        return None
    lapsed = support.lapsed_session(user_id)
    if lapsed is not None:
        _expire_later(request, lapsed)
        return _deny(request, tenant, "support_session_expired")
    if status is None and support.ended_recently(user_id):
        return _deny(request, tenant, "support_session_expired")
    return _deny(request, tenant, "not_a_member" if status is None else "membership_inactive")


def sign_in_guard(request: HttpRequest, user: object) -> str | None:
    """``IDENTITY_SIGN_IN_GUARDS`` hook. On a tenant host a correct password is not enough.
    The caller answers every refusal with the same generic invalid-credentials error (D7);
    the reason returned here is only for the audit log.

    * active members of an active or offboarding tenant: allowed;
    * suspended tenant: only active owners (restricted mode, D2);
    * platform staff without a membership: only with a usable support session of this tenant
      that is active (never on a suspended tenant, S10)."""
    tenant: TenantContext | None = getattr(request, "tenant", None)
    if tenant is None:
        return None
    user_id = getattr(user, "pk", None)
    status = membership_status(user_id)
    if tenant.status == TenantStatus.SUSPENDED:
        if status == Membership.Status.ACTIVE and is_active_owner(user_id):
            return None
        return "tenant_suspended"
    if status == Membership.Status.ACTIVE:
        return None
    if tenant.status == TenantStatus.ACTIVE and support.usable_session(user_id) is not None:
        return None
    return "not_a_member" if status is None else "membership_inactive"


def now() -> Any:  # small seam for tests
    return timezone.now()
