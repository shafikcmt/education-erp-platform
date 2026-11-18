"""Tenant roles: read-only system copies of the templates, clones, and their sync (Phase 3 M4;
plan §4.1, §9.5, §6.3 P7; owner decision Q5).

* Every tenant gets a **system copy** of each role template (``kind = tenant``, ``is_system``,
  ``template`` set). Copies are read-only for the tenant and are brought back in line with
  their template by :func:`sync_system_copies` (platform operation P7).
* A tenant customises by **cloning** a role into an ordinary tenant role, which is never synced.

``rbac_role`` has no row-level security before M6, so every query here filters on
``tenant_id`` explicitly. The functions take the tenant id only: ``rbac`` never imports
``tenancy``. Callers run them inside that tenant's transaction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models, transaction

from apps.audit.services import record
from apps.rbac.engine import ScopeTarget, bump_tenant_version, effective_permissions, require_perm
from apps.rbac.models import Role, RoleKind, RolePermission
from apps.rbac.services import GuardRailViolation

if TYPE_CHECKING:
    from django.http import HttpRequest

    from apps.identity.models import User


@dataclass
class CopyResult:
    roles: int = 0
    created: int = 0
    permissions_added: int = 0
    permissions_removed: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.created or self.permissions_added or self.permissions_removed)


def tenant_roles(tenant_id: uuid.UUID) -> models.QuerySet[Role]:
    """The roles of ONE tenant (system copies and custom roles); never another tenant's."""
    return Role.objects.filter(tenant_id=tenant_id, kind=RoleKind.TENANT)


def system_role(tenant_id: uuid.UUID, template_code: str) -> Role:
    return tenant_roles(tenant_id).get(is_system=True, template__code=template_code)


def role_codes(role: Role) -> set[str]:
    return set(
        RolePermission.objects.filter(
            role=role, permission__deprecated_at__isnull=True
        ).values_list("permission__code", flat=True)
    )


@transaction.atomic
def sync_system_copies(tenant_id: uuid.UUID) -> CopyResult:
    """Create missing system copies and make every copy equal to its template. Idempotent.

    Used at provisioning (all copies are created) and by P7 after a template change."""
    result = CopyResult()
    templates = Role.objects.filter(kind=RoleKind.TEMPLATE, tenant_id__isnull=True)
    copies = {r.template_id: r for r in tenant_roles(tenant_id).filter(template__isnull=False)}
    for template in templates:
        copy = copies.get(template.pk)
        fields = {
            "code": template.code,
            "name": template.name,
            "name_i18n": template.name_i18n,
            "description": template.description,
            "institution_types": template.institution_types,
        }
        if copy is None:
            copy = Role.objects.create(
                tenant_id=tenant_id,
                kind=RoleKind.TENANT,
                is_system=True,
                template=template,
                **fields,
            )
            result.created += 1
        elif any(getattr(copy, k) != v for k, v in fields.items()):
            for key, value in fields.items():
                setattr(copy, key, value)
            copy.save()
        wanted = dict(
            RolePermission.objects.filter(role=template).values_list(
                "permission__code", "permission_id"
            )
        )
        current = set(
            RolePermission.objects.filter(role=copy).values_list("permission__code", flat=True)
        )
        removed, _ = (
            RolePermission.objects.filter(role=copy).exclude(permission__code__in=wanted).delete()
        )
        added = [code for code in wanted if code not in current]
        RolePermission.objects.bulk_create(
            [RolePermission(role=copy, permission_id=wanted[c], tenant_id=tenant_id) for c in added]
        )
        result.roles += 1
        result.permissions_added += len(added)
        result.permissions_removed += removed
    if result.changed:
        bump_tenant_version(tenant_id)
    return result


@transaction.atomic
def clone_role(
    *,
    actor: User,
    tenant_id: uuid.UUID,
    source: Role,
    code: str,
    name: str,
    request: HttpRequest | None = None,
) -> Role:
    """Clone a role of this tenant into an editable (non-system) tenant role.

    The actor needs ``rbac.role.clone`` in the tenant scope and must hold every permission of
    the source there (no self-escalation). The clone has no template and is never synced."""
    target = ScopeTarget(tenant_id=tenant_id)
    require_perm(actor, "rbac.role.clone", target=target, use_cache=False)
    if source.tenant_id != tenant_id or source.kind != RoleKind.TENANT:
        raise ValidationError({"source": "Unknown role."})
    codes = role_codes(source)
    if codes - effective_permissions(actor, target, use_cache=False):
        raise GuardRailViolation(
            "privilege_escalation", "You cannot clone a role with permissions you do not hold."
        )
    if tenant_roles(tenant_id).filter(code=code).exists():
        raise ValidationError({"code": "A role with this code already exists."})
    clone = Role.objects.create(
        tenant_id=tenant_id,
        kind=RoleKind.TENANT,
        is_system=False,
        code=code,
        name=name,
        name_i18n={},
        description=source.description,
        institution_types=source.institution_types,
    )
    RolePermission.objects.bulk_create(
        [
            RolePermission(role=clone, permission_id=pid, tenant_id=tenant_id)
            for pid in RolePermission.objects.filter(role=source).values_list(
                "permission_id", flat=True
            )
        ]
    )
    bump_tenant_version(tenant_id)
    record(
        "rbac.role.created",
        actor=actor,
        request=request,
        target_type="rbac.role",
        target_id=clone.pk,
        metadata={"role_code": clone.code},
    )
    return clone
