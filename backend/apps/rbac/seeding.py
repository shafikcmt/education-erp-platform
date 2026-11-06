"""Idempotent sync of the permission registry and system roles (``sync_permissions`` /
``seed_roles``). Run after every ``migrate`` (the compose ``migrate`` service does this)."""

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.rbac.engine import bump_cache_version
from apps.rbac.models import Permission, Role, RoleKind, RolePermission
from apps.rbac.registry import declared_permissions
from apps.rbac.role_templates import ALL, PLATFORM_ROLES, TEMPLATE_ROLES


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    deprecated: int = 0


@transaction.atomic
def sync_permissions() -> SyncResult:
    result = SyncResult()
    specs = declared_permissions()
    existing = {p.code: p for p in Permission.objects.select_for_update()}
    for code, spec in specs.items():
        values = {
            "module_code": spec.module_code,
            "description": spec.description,
            "is_sensitive": spec.is_sensitive,
            "requires_mfa": spec.requires_mfa,
            "requires_step_up": spec.requires_step_up,
            "deprecated_at": None,
        }
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
    return result


@transaction.atomic
def seed_roles() -> int:
    """Create/refresh system roles. System role permissions always match the data file."""
    registered = set(
        Permission.objects.filter(deprecated_at__isnull=True).values_list("code", flat=True)
    )
    count = 0
    for kind, rows in ((RoleKind.PLATFORM, PLATFORM_ROLES), (RoleKind.TEMPLATE, TEMPLATE_ROLES)):
        for row in rows:
            role, _ = Role.objects.update_or_create(
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
            wanted = (
                registered
                if ALL in row["permissions"]
                else {c for c in [*row["permissions"], *row["planned"]] if c in registered}
            )
            current = set(role.role_permissions.values_list("permission__code", flat=True))
            RolePermission.objects.filter(role=role).exclude(permission__code__in=wanted).delete()
            perms = Permission.objects.filter(code__in=wanted - current)
            RolePermission.objects.bulk_create(
                [RolePermission(role=role, permission=p) for p in perms]
            )
            count += 1
    bump_cache_version()
    return count
