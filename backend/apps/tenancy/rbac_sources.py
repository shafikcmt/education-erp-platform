"""Tenant permission source (Phase 3 M4; plan §9.3; ADR-044).

``TenantMembershipSource`` grants the union of a member's role assignments that are in force
and whose scope **covers** the target (tenant ⊇ institution ⊇ campus, never sideways).

Fail closed:

* nothing for platform targets, and nothing unless the target's tenant is the one applied to
  the current transaction (so RLS agrees with what is read);
* the membership must be ``active``; the tenant must be ``active``. While a tenant is
  ``offboarding`` only its owners keep their grants (the request gate refuses writes); while
  it is ``suspended`` only its owners keep the restricted-mode codes (D2);
* revoked, not-yet-valid and expired assignments never count (checked at evaluation time).

Loaded by the rbac engine from ``settings.RBAC_PERMISSION_SOURCES``; ``rbac`` never imports
this module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import connection
from django.db.models import Q
from django.utils import timezone

from apps.core.tenancy import current_tenant
from apps.core.tenancy.transaction import applied_tenant_id
from apps.rbac.engine import ScopeGrant, ScopeTarget
from apps.rbac.models import Permission, RoleAssignment, RolePermission
from apps.rbac.role_templates import SUSPENDED_OWNER_CODES, TENANT_OWNER
from apps.tenancy.models import Membership, Tenant
from apps.tenancy.rules import TenantStatus

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser


def live_assignments() -> Q:
    """Assignments in force right now (not revoked, inside their validity window)."""
    now = timezone.now()
    return Q(revoked_at__isnull=True, valid_from__lte=now) & (
        Q(valid_until__isnull=True) | Q(valid_until__gt=now)
    )


class TenantMembershipSource:
    def grants(self, actor: AbstractBaseUser, target: ScopeTarget) -> frozenset[str]:
        if target.tenant_id is None:
            return frozenset()
        ctx = current_tenant()
        if ctx is None or ctx.id != target.tenant_id or applied_tenant_id(connection) != ctx.id:
            return frozenset()
        status = Tenant.objects.filter(pk=ctx.id).values_list("status", flat=True).first()
        if status not in (TenantStatus.ACTIVE, TenantStatus.OFFBOARDING, TenantStatus.SUSPENDED):
            return frozenset()
        rows = RoleAssignment.objects.filter(
            live_assignments(),
            membership__user_id=actor.pk,
            membership__status=Membership.Status.ACTIVE,
        ).values_list(
            "role_id", "institution_id", "campus_id", "role__is_system", "role__template__code"
        )
        role_ids = set()
        for role_id, institution_id, campus_id, is_system, template_code in rows:
            is_owner = is_system and template_code == TENANT_OWNER
            # Offboarding: only owners keep their grants. Suspended: only owners, and only
            # the restricted-mode codes (D2), applied below.
            if status != TenantStatus.ACTIVE and not is_owner:
                continue
            if ScopeGrant(ctx.id, institution_id, campus_id).covers(target):
                role_ids.add(role_id)
        if not role_ids:
            return frozenset()
        codes = frozenset(
            RolePermission.objects.filter(
                role_id__in=role_ids,
                role__tenant_id=ctx.id,  # rbac_role has no RLS before M6: always filter
                permission__deprecated_at__isnull=True,
            ).values_list("permission__code", flat=True)
        )
        if status == TenantStatus.SUSPENDED:
            return codes & SUSPENDED_OWNER_CODES
        return codes

    def scope_targets(self, actor: AbstractBaseUser, tenant_id: object) -> list[ScopeTarget]:
        """The scopes of the actor's live assignments in the applied tenant (for the MFA
        requirement, which must see institution- and campus-scoped privileges too)."""
        ctx = current_tenant()
        if ctx is None or ctx.id != tenant_id or applied_tenant_id(connection) != ctx.id:
            return []
        rows = (
            RoleAssignment.objects.filter(
                live_assignments(),
                membership__user_id=actor.pk,
                membership__status=Membership.Status.ACTIVE,
            )
            .values_list("institution_id", "campus_id")
            .distinct()
        )
        return [ScopeTarget(ctx.id, inst, campus) for inst, campus in rows]


class SupportSessionSource:
    """Read-only grants of an approved support session (Phase 3 M5; plan §9.3, §11.2 S3).

    Only for a usable session of the actor in the tenant applied to the current transaction,
    only while that tenant is ``active`` (D2: never on a suspended tenant), and only the view
    codes flagged ``support_readable``. Approval and every other code are never granted, so
    staff can't approve their own session (S6)."""

    def grants(self, actor: AbstractBaseUser, target: ScopeTarget) -> frozenset[str]:
        if target.tenant_id is None:
            return frozenset()
        ctx = current_tenant()
        if ctx is None or ctx.id != target.tenant_id or applied_tenant_id(connection) != ctx.id:
            return frozenset()
        status = Tenant.objects.filter(pk=ctx.id).values_list("status", flat=True).first()
        if status != TenantStatus.ACTIVE:
            return frozenset()
        from apps.tenancy.support import usable_session

        if usable_session(actor.pk) is None:
            return frozenset()
        return frozenset(
            Permission.objects.filter(
                support_readable=True, deprecated_at__isnull=True
            ).values_list("code", flat=True)
        )
