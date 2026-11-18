"""Owner-only, idempotent sync of the permission catalogue and system roles (``sync_permissions``
/ ``seed_roles``). Phase 3 M1 / O1.

* They run **only as the database owner role**, in the one-shot ``migrate`` bootstrap step
  right after ``migrate`` (compose ``migrate`` service). The runtime role ``erp_app`` has only
  SELECT on ``rbac_permission`` (``rbac.0003``), and both functions refuse to start as
  ``erp_app`` before touching anything (code guard on top of the database grant).
* Every run is audited (``rbac.permission_catalog.synced``, ``rbac.system_roles.seeded``) with
  what changed, so catalogue updates are traceable to a deployment.
* Runtime code that needs the catalogue only reads it: :func:`catalog_drift` reports whether
  the database matches the declared manifests and role templates (``create_platform_admin``
  refuses to run while it doesn't).
"""

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.audit.models import ActorType
from apps.audit.services import record
from apps.core.db_operations import require_owner_role
from apps.rbac.engine import bump_cache_version
from apps.rbac.models import Permission, Role, RoleKind, RolePermission
from apps.rbac.registry import declared_permissions
from apps.rbac.role_templates import ALL, PLATFORM_ROLES, TEMPLATE_ROLES

_SPEC_FIELDS = (
    "module_code",
    "description",
    "is_sensitive",
    "requires_mfa",
    "requires_step_up",
    "support_readable",
)


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    deprecated: int = 0


@dataclass
class SeedResult:
    roles: int = 0
    roles_created: int = 0
    permissions_added: int = 0
    permissions_removed: int = 0


@transaction.atomic
def sync_permissions() -> SyncResult:
    require_owner_role("sync_permissions")
    result = SyncResult()
    specs = declared_permissions()
    existing = {p.code: p for p in Permission.objects.select_for_update()}
    for code, spec in specs.items():
        values = {field: getattr(spec, field) for field in _SPEC_FIELDS}
        values["deprecated_at"] = None
        row = existing.get(code)
        if row is None:
            Permission.objects.create(code=code, **values)
            result.created += 1
        elif any(getattr(row, k) != v for k, v in values.items()):
            for key, value in values.items():
                setattr(row, key, value)
            row.save()
            result.updated += 1
    for code, row in existing.items():
        if code not in specs and row.deprecated_at is None:
            row.deprecated_at = timezone.now()
            row.save(update_fields=["deprecated_at", "updated_at"])
            result.deprecated += 1
    bump_cache_version()
    record(
        "rbac.permission_catalog.synced",
        actor_type=ActorType.SYSTEM,
        metadata={
            "created": result.created,
            "updated": result.updated,
            "deprecated": result.deprecated,
            "declared": len(specs),
        },
    )
    return result


def _wanted_permissions(row: dict[str, Any], registered: set[str]) -> set[str]:
    if ALL in row["permissions"]:
        return set(registered)
    return {c for c in [*row["permissions"], *row["planned"]] if c in registered}


def _role_rows() -> list[tuple[str, dict[str, Any]]]:
    return [(RoleKind.PLATFORM, r) for r in PLATFORM_ROLES] + [
        (RoleKind.TEMPLATE, r) for r in TEMPLATE_ROLES
    ]


@transaction.atomic
def seed_roles() -> SeedResult:
    """Create/refresh system roles. System role permissions always match the data file."""
    require_owner_role("seed_roles")
    registered = set(
        Permission.objects.filter(deprecated_at__isnull=True).values_list("code", flat=True)
    )
    result = SeedResult()
    for kind, row in _role_rows():
        role, created = Role.objects.update_or_create(
            tenant_id=None,
            code=row["code"],
            defaults={
                "name": row["name"],
                "name_i18n": {"en": row["name"], "bn": row["bn"]},
                "description": row["description"],
                "kind": kind,
                "institution_types": row.get("institution_types", []),
                "is_system": True,
            },
        )
        wanted = _wanted_permissions(row, registered)
        current = set(role.role_permissions.values_list("permission__code", flat=True))
        removed, _ = (
            RolePermission.objects.filter(role=role).exclude(permission__code__in=wanted).delete()
        )
        perms = list(Permission.objects.filter(code__in=wanted - current))
        RolePermission.objects.bulk_create([RolePermission(role=role, permission=p) for p in perms])
        result.roles += 1
        result.roles_created += int(created)
        result.permissions_added += len(perms)
        result.permissions_removed += removed
    bump_cache_version()
    record(
        "rbac.system_roles.seeded",
        actor_type=ActorType.SYSTEM,
        metadata={
            "roles": result.roles,
            "created": result.roles_created,
            "added": result.permissions_added,
            "removed": result.permissions_removed,
        },
    )
    return result


def catalog_drift() -> list[str]:
    """Read-only: differences between the database and the declared catalogue/system roles."""
    problems: list[str] = []
    specs = declared_permissions()
    rows = {p.code: p for p in Permission.objects.all()}
    for code, spec in sorted(specs.items()):
        row = rows.get(code)
        if row is None:
            problems.append(f"permission {code} missing")
        elif row.deprecated_at is not None or any(
            getattr(row, f) != getattr(spec, f) for f in _SPEC_FIELDS
        ):
            problems.append(f"permission {code} out of date")
    registered = {c for c, r in rows.items() if r.deprecated_at is None and c in specs}
    roles = {r.code: r for r in Role.objects.filter(tenant_id__isnull=True, is_system=True)}
    for _, template in _role_rows():
        role = roles.get(template["code"])
        if role is None:
            problems.append(f"system role {template['code']} missing")
            continue
        have = set(role.role_permissions.values_list("permission__code", flat=True))
        if have != _wanted_permissions(template, registered):
            problems.append(f"system role {template['code']} permissions out of date")
    return problems
