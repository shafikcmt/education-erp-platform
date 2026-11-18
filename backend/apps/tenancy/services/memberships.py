"""Member lifecycle: suspend, reactivate, remove (Phase 3 M4; plan §9.5, §9.6).

* Acting on a member needs the permission at tenant scope **and** every permission that member
  holds (ADR-040 H2, extended to tenants): a lower-privileged admin can't suspend the owner.
* The last active tenant owner can't be suspended or removed.
* Suspension and removal end the member's sessions on this tenant's hosts and take effect on
  the next request (the membership is checked uncached on every tenant request).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from apps.audit.services import record
from apps.identity.models import SessionRecord
from apps.identity.services import sessions
from apps.rbac.engine import ScopeTarget, bump_tenant_version, effective_permissions, require_perm
from apps.rbac.models import RoleAssignment
from apps.rbac.services import GuardRailViolation
from apps.tenancy.models import Membership, TenantDomain
from apps.tenancy.services import common
from apps.tenancy.services.assignments import end_assignments

if TYPE_CHECKING:
    from django.http import HttpRequest

    from apps.identity.models import User


def _authorise(actor: User, membership: Membership, code: str) -> ScopeTarget:
    ctx = common.tenant_context()
    target = ScopeTarget(tenant_id=ctx.id)
    require_perm(actor, code, target=target, use_cache=False)
    if membership.user_id == actor.pk:
        raise GuardRailViolation("cannot_act_on_self", "You cannot do this to yourself.")
    if common.member_codes(membership) - effective_permissions(actor, target, use_cache=False):
        raise GuardRailViolation(
            "insufficient_privilege",
            "You cannot do this to a member with more privileges than yours.",
        )
    return target


def revoke_tenant_sessions(membership: Membership, *, reason: str) -> int:
    """End the member's sessions on THIS tenant's hosts only (sessions are per host)."""
    hosts = list(TenantDomain.objects.values_list("domain", flat=True))
    if not hosts:
        return 0
    return sessions.revoke_records(
        SessionRecord.objects.filter(user_id=membership.user_id, host__in=hosts), reason=reason
    )


def _audit(action: str, actor: User, membership: Membership, request: HttpRequest | None) -> None:
    record(
        action,
        actor=actor,
        request=request,
        target_type="tenancy.membership",
        target_id=membership.pk,
    )


@transaction.atomic
def suspend_member(
    *, actor: User, membership: Membership, request: HttpRequest | None = None
) -> Membership:
    ctx = common.tenant_context()
    common.lock_tenant(ctx)
    membership = Membership.objects.get(pk=membership.pk)
    _authorise(actor, membership, "tenancy.member.update")
    if membership.status != Membership.Status.ACTIVE:
        return membership
    common.assert_not_last_owner(membership.pk)
    membership.status = Membership.Status.SUSPENDED
    membership.suspended_at = timezone.now()
    membership.save(update_fields=["status", "suspended_at", "updated_at"])
    bump_tenant_version(ctx.id)
    revoke_tenant_sessions(membership, reason="membership_suspended")
    _audit("tenancy.member.suspended", actor, membership, request)
    return membership


@transaction.atomic
def reactivate_member(
    *, actor: User, membership: Membership, request: HttpRequest | None = None
) -> Membership:
    ctx = common.tenant_context()
    membership = Membership.objects.get(pk=membership.pk)
    _authorise(actor, membership, "tenancy.member.update")
    if membership.status != Membership.Status.SUSPENDED:
        return membership
    membership.status = Membership.Status.ACTIVE
    membership.suspended_at = None
    membership.save(update_fields=["status", "suspended_at", "updated_at"])
    bump_tenant_version(ctx.id)
    _audit("tenancy.member.reactivated", actor, membership, request)
    return membership


@transaction.atomic
def remove_member(
    *, actor: User, membership: Membership, request: HttpRequest | None = None
) -> Membership:
    """Membership becomes ``left``; its assignments are revoked; its tenant sessions end.
    Rows are kept (history, audit, composite keys)."""
    ctx = common.tenant_context()
    common.lock_tenant(ctx)
    membership = Membership.objects.get(pk=membership.pk)
    _authorise(actor, membership, "tenancy.member.remove")
    if membership.status == Membership.Status.LEFT:
        return membership
    common.assert_not_last_owner(membership.pk)
    membership.status = Membership.Status.LEFT
    membership.save(update_fields=["status", "updated_at"])
    end_assignments(RoleAssignment.objects.filter(membership=membership), revoked_by=actor.pk)
    revoke_tenant_sessions(membership, reason="membership_removed")
    _audit("tenancy.member.removed", actor, membership, request)
    return membership
