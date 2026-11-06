"""Role and platform-role services with guard rails (Phase 2 plan §5.1).

Guard rails:
* **No self-escalation:** an actor can only put permissions they hold into a role, and can only
  grant a role whose permissions they all hold.
* Only an existing ``super_admin`` (in step-up mode, enforced by the API) can grant ``super_admin``.
* The last active ``super_admin`` can't be demoted (or deactivated: see identity services).
* System roles are read-only. Every change is audited in the same transaction.
Security-critical checks bypass the permission cache.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import record
from apps.rbac.engine import bump_cache_version, effective_permissions, require_perm
from apps.rbac.models import Permission, PlatformRoleAssignment, Role, RoleKind, RolePermission

if TYPE_CHECKING:
    from django.http import HttpRequest

    from apps.identity.models import User

SUPER_ADMIN = "super_admin"


class GuardRailViolation(PermissionDenied):
    """A request that would break an RBAC invariant (self-escalation, last super admin, ...)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _assert_holds_all(actor: User, codes: set[str]) -> None:
    held = effective_permissions(actor, use_cache=False)
    missing = codes - held
    if missing:
        raise GuardRailViolation(
            "privilege_escalation", "You cannot grant permissions you do not hold."
        )


def _resolve_permissions(codes: list[str]) -> list[Permission]:
    found = list(Permission.objects.filter(code__in=codes, deprecated_at__isnull=True))
    if len(found) != len(set(codes)):
        raise ValidationError({"permissions": "Unknown or deprecated permission code."})
    return found


def active_super_admin_count(*, exclude_user_id: Any = None) -> int:
    qs = PlatformRoleAssignment.objects.filter(
        role__code=SUPER_ADMIN, role__kind=RoleKind.PLATFORM, user__is_active=True
    )
    if exclude_user_id is not None:
        qs = qs.exclude(user_id=exclude_user_id)
    return qs.values("user_id").distinct().count()


def is_super_admin(user: User) -> bool:
    return PlatformRoleAssignment.objects.filter(
        user_id=user.pk, role__code=SUPER_ADMIN, role__kind=RoleKind.PLATFORM
    ).exists()


def assert_not_last_super_admin(user: User) -> None:
    if is_super_admin(user) and active_super_admin_count(exclude_user_id=user.pk) == 0:
        raise GuardRailViolation(
            "last_super_admin", "The last active Super Admin cannot be removed or deactivated."
        )


def assert_can_act_on(actor: User, target: User, code: str) -> None:
    """Privileged-target protection (review H2), enforced in services, not only in views.

    The actor must hold ``code`` (checked without the cache) **and** at least every permission
    the target account holds; only a Super Admin may act on another Super Admin.
    """
    from apps.rbac.engine import assigned_permissions

    require_perm(actor, code, use_cache=False)
    if is_super_admin(target) and not is_super_admin(actor):
        raise GuardRailViolation(
            "insufficient_privilege", "Only a Super Admin can do this to a Super Admin."
        )
    missing = assigned_permissions(target) - effective_permissions(actor, use_cache=False)
    if missing:
        raise GuardRailViolation(
            "insufficient_privilege",
            "You cannot do this to an account with more privileges than yours.",
        )


def _set_permissions(role: Role, permissions: list[Permission]) -> tuple[list[str], list[str]]:
    current = {rp.permission.code: rp for rp in role.role_permissions.select_related("permission")}
    wanted = {p.code: p for p in permissions}
    added = sorted(set(wanted) - set(current))
    removed = sorted(set(current) - set(wanted))
    RolePermission.objects.filter(role=role, permission__code__in=removed).delete()
    RolePermission.objects.bulk_create(
        [RolePermission(role=role, permission=wanted[c], tenant_id=role.tenant_id) for c in added]
    )
    bump_cache_version()  # bulk operations don't send model signals
    return added, removed


@transaction.atomic
def create_role(
    *,
    actor: User,
    code: str,
    name: str,
    permissions: list[str],
    description: str = "",
    name_i18n: dict[str, str] | None = None,
    request: HttpRequest | None = None,
) -> Role:
    require_perm(actor, "rbac.role.create", use_cache=False)
    perms = _resolve_permissions(permissions)
    _assert_holds_all(actor, {p.code for p in perms})
    if Role.objects.filter(tenant_id__isnull=True, code=code).exists():
        raise ValidationError({"code": "A role with this code already exists."})
    role = Role.objects.create(
        code=code,
        name=name,
        description=description,
        name_i18n=name_i18n or {},
        kind=RoleKind.PLATFORM,
        is_system=False,
    )
    _set_permissions(role, perms)
    record(
        "rbac.role.created",
        actor=actor,
        request=request,
        target_type="rbac.role",
        target_id=role.pk,
        metadata={"role_code": code},
    )
    return role


@transaction.atomic
def update_role(
    *,
    actor: User,
    role: Role,
    changes: dict[str, Any],
    request: HttpRequest | None = None,
) -> Role:
    require_perm(actor, "rbac.role.update", use_cache=False)
    role = Role.objects.select_for_update().get(pk=role.pk)
    if role.is_system:
        raise GuardRailViolation("system_role_read_only", "System roles are read-only.")
    fields = [f for f in ("name", "description", "name_i18n") if f in changes]
    for field in fields:
        setattr(role, field, changes[field])
    if fields:
        role.save(update_fields=[*fields, "updated_at"])
        record(
            "rbac.role.updated",
            actor=actor,
            request=request,
            target_type="rbac.role",
            target_id=role.pk,
            metadata={"role_code": role.code, "fields": fields},
        )
    if "permissions" in changes:
        perms = _resolve_permissions(changes["permissions"])
        _assert_holds_all(actor, {p.code for p in perms})
        added, removed = _set_permissions(role, perms)
        if added or removed:
            record(
                "rbac.role.permissions_changed",
                actor=actor,
                request=request,
                target_type="rbac.role",
                target_id=role.pk,
                metadata={"role_code": role.code, "added": added, "removed": removed},
            )
    return role


@transaction.atomic
def delete_role(*, actor: User, role: Role, request: HttpRequest | None = None) -> None:
    require_perm(actor, "rbac.role.delete", use_cache=False)
    if role.is_system:
        raise GuardRailViolation("system_role_read_only", "System roles are read-only.")
    if role.platform_assignments.exists():
        raise GuardRailViolation("role_in_use", "Revoke this role from all users first.")
    code, pk = role.code, role.pk
    role.delete()
    record(
        "rbac.role.deleted",
        actor=actor,
        request=request,
        target_type="rbac.role",
        target_id=pk,
        metadata={"role_code": code},
    )


@transaction.atomic
def grant_platform_role(
    *,
    actor: User,
    user: User,
    role: Role,
    reason: str = "",
    request: HttpRequest | None = None,
) -> PlatformRoleAssignment:
    require_perm(actor, "rbac.platform_role.assign", use_cache=False)
    if role.kind != RoleKind.PLATFORM:
        raise ValidationError({"role": "Only platform roles can be assigned here."})
    if role.code == SUPER_ADMIN and not is_super_admin(actor):
        raise GuardRailViolation(
            "privilege_escalation", "Only a Super Admin can grant the Super Admin role."
        )
    _assert_holds_all(actor, set(role.permissions.values_list("code", flat=True)))
    assignment, created = PlatformRoleAssignment.objects.get_or_create(
        user=user,
        role=role,
        defaults={"granted_by": actor, "granted_at": timezone.now(), "reason": reason[:255]},
    )
    if created:
        record(
            "rbac.platform_role.granted",
            actor=actor,
            request=request,
            target_type="identity.user",
            target_id=user.pk,
            metadata={"role_code": role.code},
        )
    return assignment


@transaction.atomic
def revoke_platform_role(
    *,
    actor: User,
    assignment: PlatformRoleAssignment,
    request: HttpRequest | None = None,
) -> None:
    require_perm(actor, "rbac.platform_role.assign", use_cache=False)
    assignment = (
        PlatformRoleAssignment.objects.select_for_update()
        .select_related("role", "user")
        .get(pk=assignment.pk)
    )
    if assignment.role.code == SUPER_ADMIN:
        if not is_super_admin(actor):
            raise GuardRailViolation(
                "privilege_escalation", "Only a Super Admin can revoke the Super Admin role."
            )
        assert_not_last_super_admin(assignment.user)
    user_id, role_code = assignment.user_id, assignment.role.code
    assignment.delete()
    record(
        "rbac.platform_role.revoked",
        actor=actor,
        request=request,
        target_type="identity.user",
        target_id=user_id,
        metadata={"role_code": role_code},
    )


def bootstrap_super_admin(*, user: User, reason: str) -> PlatformRoleAssignment:
    """Used only by ``create_platform_admin`` (no actor exists yet). Audited as ``system``."""
    role = Role.objects.get(tenant_id__isnull=True, code=SUPER_ADMIN, kind=RoleKind.PLATFORM)
    assignment, created = PlatformRoleAssignment.objects.get_or_create(
        user=user, role=role, defaults={"granted_at": timezone.now(), "reason": reason[:255]}
    )
    if created:
        record(
            "rbac.platform_role.granted",
            target_type="identity.user",
            target_id=user.pk,
            metadata={"role_code": SUPER_ADMIN},
        )
    return assignment
