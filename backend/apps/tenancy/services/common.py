"""Shared helpers of the tenant services (scope targets, owner counting, guard rails)."""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import connection

from apps.core.tenancy import TenantContext, require_tenant
from apps.core.tenancy.exceptions import TenantContextNotApplied
from apps.core.tenancy.transaction import applied_tenant_id
from apps.rbac.engine import ScopeTarget, effective_permissions
from apps.rbac.models import AssignmentScope, Role, RoleAssignment, RoleKind
from apps.rbac.role_templates import TENANT_OWNER
from apps.rbac.services import GuardRailViolation
from apps.rbac.tenant_roles import role_codes
from apps.tenancy.models import Campus, Institution, Membership, Tenant
from apps.tenancy.rbac_sources import live_assignments


def tenant_context() -> TenantContext:
    """The tenant of the current transaction; refuses to work outside one."""
    ctx = require_tenant()
    if applied_tenant_id(connection) != ctx.id:
        raise TenantContextNotApplied("Tenant services run inside tenant_atomic().")
    return ctx


def lock_tenant(ctx: TenantContext) -> Tenant:
    """Serialise privilege-changing operations of one tenant (last-owner rule, limits)."""
    return Tenant.objects.select_for_update().get(pk=ctx.id)


def resolve_scope(
    ctx: TenantContext, scope_type: str, institution: Any = None, campus: Any = None
) -> tuple[ScopeTarget, Institution | None, Campus | None]:
    """Validate a scope and return its target. Objects of other tenants are invisible (RLS),
    so a foreign id fails exactly like an unknown one."""
    inst = _load(Institution, institution)
    camp = _load(Campus, campus)
    if scope_type == AssignmentScope.TENANT and inst is None and camp is None:
        return ScopeTarget(tenant_id=ctx.id), None, None
    if scope_type == AssignmentScope.INSTITUTION and inst is not None and camp is None:
        return ScopeTarget(tenant_id=ctx.id, institution_id=inst.pk), inst, None
    if (
        scope_type == AssignmentScope.CAMPUS
        and inst is not None
        and camp is not None
        and camp.institution_id == inst.pk
    ):
        return ScopeTarget(ctx.id, inst.pk, camp.pk), inst, camp
    raise ValidationError({"scope": "Invalid scope."})


def _load(model: Any, value: Any) -> Any:
    if value is None or isinstance(value, model):
        return value
    found = model.objects.filter(pk=value, archived_at__isnull=True).first()
    if found is None:
        raise ValidationError({"scope": "Invalid scope."})
    return found


def tenant_role(ctx: TenantContext, role: Role | uuid.UUID | str) -> Role:
    """A role of THIS tenant; templates, platform roles and other tenants' roles are refused."""
    pk = role.pk if isinstance(role, Role) else role
    found = Role.objects.filter(pk=pk, tenant_id=ctx.id, kind=RoleKind.TENANT).first()
    if found is None:
        raise ValidationError({"role": "Unknown role."})
    return found


def assert_no_escalation(actor: Any, role: Role, target: ScopeTarget) -> None:
    """Nobody hands out permissions they don't hold in that scope (plan §9.5)."""
    if role_codes(role) - effective_permissions(actor, target, use_cache=False):
        raise GuardRailViolation(
            "privilege_escalation", "You cannot grant permissions you do not hold in this scope."
        )


def is_owner_role(role: Role) -> bool:
    template = role.template if role.is_system else None
    return template is not None and template.code == TENANT_OWNER


def active_owner_ids(*, excluding_assignment: uuid.UUID | None = None) -> set[uuid.UUID]:
    """Memberships that are active tenant owners right now (tenant-scope owner assignment)."""
    rows = RoleAssignment.objects.filter(
        live_assignments(),
        scope_type=AssignmentScope.TENANT,
        role__is_system=True,
        role__template__code=TENANT_OWNER,
        membership__status=Membership.Status.ACTIVE,
    )
    if excluding_assignment is not None:
        rows = rows.exclude(pk=excluding_assignment)
    return set(rows.values_list("membership_id", flat=True))


def assert_not_last_owner(
    membership_id: uuid.UUID, *, excluding_assignment: uuid.UUID | None = None
) -> None:
    """The last active tenant owner can't be removed, suspended or demoted (plan §9.5).

    ``excluding_assignment``: the assignment about to be revoked (demotion). Without it, the
    membership itself is about to stop counting (suspension or removal)."""
    if excluding_assignment is None:
        remaining = active_owner_ids() - {membership_id}
        affected = membership_id in active_owner_ids()
    else:
        remaining = active_owner_ids(excluding_assignment=excluding_assignment)
        affected = membership_id in active_owner_ids() and membership_id not in remaining
    if affected and not remaining:
        raise GuardRailViolation(
            "last_tenant_owner", "The organisation must keep at least one active owner."
        )


def member_codes(membership: Membership) -> set[str]:
    """Every permission a member holds through live assignments, in any scope."""
    roles = Role.objects.filter(
        tenant_id=membership.tenant_id,
        pk__in=RoleAssignment.objects.filter(live_assignments(), membership=membership).values(
            "role_id"
        ),
    )
    codes: set[str] = set()
    for role in roles:
        codes |= role_codes(role)
    return codes


def institution_preset(institution_type: str) -> dict[str, str]:
    """Preset pin for a new institution (``TENANCY_INSTITUTION_PRESET`` hook, Phase 5 M2).
    Tenancy never imports the customization app."""
    from django.conf import settings
    from django.utils.module_loading import import_string

    hook = getattr(settings, "TENANCY_INSTITUTION_PRESET", "")
    code, version = import_string(hook)(institution_type) if hook else ("", "")
    return {"preset_code": code, "preset_version": version}


def custom_fields_hook(name: str) -> Any:
    """A function of the custom field module (``TENANCY_CUSTOM_FIELDS``), or ``None``."""
    from django.conf import settings
    from django.utils.module_loading import import_string

    module = getattr(settings, "TENANCY_CUSTOM_FIELDS", "")
    return import_string(f"{module}.{name}") if module else None


def merge_extra(entity: str, current: Any, incoming: Any, actor: Any, target: Any) -> Any:
    hook = custom_fields_hook("merge_for_update")
    if hook is None:
        raise ValidationError({"extra": "Custom fields are not available."})
    return hook(entity, current, incoming, actor, target)
