"""Granting and revoking tenant role assignments (Phase 3 M4; plan §9.5, §9.6).

Guard rails:

* the actor needs ``rbac.assignment.manage`` **in the scope of the assignment**, so a campus
  admin can't grant at institution or tenant scope;
* nobody grants (or takes away) a role holding permissions they don't hold in that scope;
* only roles of this tenant can be assigned (system copies or custom roles, never templates);
* the last active tenant owner can't be demoted.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import record
from apps.rbac.engine import ScopeTarget, bump_tenant_version, require_perm
from apps.rbac.models import Role, RoleAssignment
from apps.tenancy.models import Membership
from apps.tenancy.services import common

if TYPE_CHECKING:
    from django.http import HttpRequest

    from apps.identity.models import User

MANAGE = "rbac.assignment.manage"


def _target_of(assignment: RoleAssignment) -> ScopeTarget:
    return ScopeTarget(assignment.tenant_id, assignment.institution_id, assignment.campus_id)


def create_assignment(
    *,
    membership: Membership,
    role: Role,
    scope_type: str,
    institution: Any = None,
    campus: Any = None,
    granted_by: Any = None,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    reason: str = "",
) -> RoleAssignment:
    """Store an assignment WITHOUT authorising an actor. For flows that authorised the grant
    earlier (accepting an invitation) or by another rule (provisioning). Idempotent for a
    live assignment of the same role in the same scope."""
    existing = RoleAssignment.objects.filter(
        membership=membership,
        role=role,
        scope_type=scope_type,
        institution=institution,
        campus=campus,
        revoked_at__isnull=True,
    ).first()
    if existing is not None:
        return existing
    assignment = RoleAssignment.objects.create(
        membership=membership,
        role=role,
        scope_type=scope_type,
        institution=institution,
        campus=campus,
        valid_from=valid_from or timezone.now(),
        valid_until=valid_until,
        granted_by=granted_by,
        reason=reason[:255],
    )
    bump_tenant_version(assignment.tenant_id)
    return assignment


@transaction.atomic
def grant_assignment(
    *,
    actor: User,
    membership: Membership,
    role: Any,
    scope_type: str,
    institution: Any = None,
    campus: Any = None,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    reason: str = "",
    request: HttpRequest | None = None,
) -> RoleAssignment:
    ctx = common.tenant_context()
    target, inst, camp = common.resolve_scope(ctx, scope_type, institution, campus)
    require_perm(actor, MANAGE, target=target, use_cache=False)
    tenant_role = common.tenant_role(ctx, role)
    common.assert_no_escalation(actor, tenant_role, target)
    if membership.status == Membership.Status.LEFT:
        raise ValidationError({"membership": "This member has left the organisation."})
    if valid_until is not None and valid_until <= (valid_from or timezone.now()):
        raise ValidationError({"valid_until": "Must be later than the start."})
    assignment = create_assignment(
        membership=membership,
        role=tenant_role,
        scope_type=scope_type,
        institution=inst,
        campus=camp,
        granted_by=actor.pk,
        valid_from=valid_from,
        valid_until=valid_until,
        reason=reason,
    )
    record(
        "rbac.assignment.granted",
        actor=actor,
        request=request,
        target_type="tenancy.membership",
        target_id=membership.pk,
        metadata={"role_code": tenant_role.code, "scope_type": scope_type},
    )
    return assignment


@transaction.atomic
def revoke_assignment(
    *, actor: User, assignment: RoleAssignment, request: HttpRequest | None = None
) -> RoleAssignment:
    ctx = common.tenant_context()
    common.lock_tenant(ctx)  # serialise with other owner changes (last-owner rule)
    assignment = RoleAssignment.objects.select_related("role", "role__template").get(
        pk=assignment.pk
    )
    target = _target_of(assignment)
    require_perm(actor, MANAGE, target=target, use_cache=False)
    # Taking a role away is as privileged as handing it out.
    common.assert_no_escalation(actor, assignment.role, target)
    if assignment.revoked_at is not None:
        return assignment
    if common.is_owner_role(assignment.role):
        common.assert_not_last_owner(assignment.membership_id, excluding_assignment=assignment.pk)
    end_assignments(RoleAssignment.objects.filter(pk=assignment.pk), revoked_by=actor.pk)
    record(
        "rbac.assignment.revoked",
        actor=actor,
        request=request,
        target_type="tenancy.membership",
        target_id=assignment.membership_id,
        metadata={"role_code": assignment.role.code, "scope_type": assignment.scope_type},
    )
    assignment.refresh_from_db()
    return assignment


def end_assignments(assignments: Any, *, revoked_by: Any) -> int:
    """Revoke live assignments (rows are kept) and invalidate this tenant's permission cache."""
    count: int = assignments.filter(revoked_at__isnull=True).update(
        revoked_at=timezone.now(), revoked_by=revoked_by, updated_at=timezone.now()
    )
    bump_tenant_version(common.tenant_context().id)
    return count
