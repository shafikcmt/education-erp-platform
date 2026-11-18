"""Tenant permission source (Phase 3 M4; plan §9.3; ADR-044).

``TenantMembershipSource`` grants the union of a member's role assignments that are in force
and whose scope **covers** the target (tenant ⊇ institution ⊇ campus, never sideways).

Fail closed:

* nothing for platform targets, and nothing unless the target's tenant is the one applied to
  the current transaction (so RLS agrees with what is read);
* the membership must be ``active``; the tenant must be ``active``. While a tenant is
  ``offboarding`` only its owners keep their grants, and the request gate refuses writes;
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
from apps.rbac.models import RoleAssignment, RolePermission
from apps.rbac.role_templates import TENANT_OWNER
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
        if status not in (TenantStatus.ACTIVE, TenantStatus.OFFBOARDING):
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
            if status == TenantStatus.OFFBOARDING and not (
                is_system and template_code == TENANT_OWNER
            ):
                continue
            if ScopeGrant(ctx.id, institution_id, campus_id).covers(target):
                role_ids.add(role_id)
        if not role_ids:
            return frozenset()
        codes = RolePermission.objects.filter(
            role_id__in=role_ids,
            role__tenant_id=ctx.id,  # rbac_role has no RLS before M6: always filter
            permission__deprecated_at__isnull=True,
        ).values_list("permission__code", flat=True)
        return frozenset(codes)
