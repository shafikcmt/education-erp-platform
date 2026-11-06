"""Phase 2 permission sources (plan §4.4). Phase 3 adds tenant membership and support sources."""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.rbac.engine import ScopeTarget

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

SELF_SERVICE_CODES = frozenset(
    {
        "identity.account.view_own",
        "identity.account.update_own",
        "identity.session.view_own",
        "identity.session.revoke_own",
        "identity.mfa.manage_own",
    }
)


class SelfServiceSource:
    """Every active user may manage their **own** account, sessions and MFA, in any scope."""

    def grants(self, actor: AbstractBaseUser, target: ScopeTarget) -> frozenset[str]:
        return SELF_SERVICE_CODES


class PlatformRoleSource:
    """Platform-role permissions, **only** for platform targets (no implicit tenant access)."""

    def grants(self, actor: AbstractBaseUser, target: ScopeTarget) -> frozenset[str]:
        if not target.is_platform:
            return frozenset()
        from apps.rbac.models import RoleKind, RolePermission

        codes = RolePermission.objects.filter(
            role__kind=RoleKind.PLATFORM,
            role__platform_assignments__user_id=actor.pk,
            permission__deprecated_at__isnull=True,
        ).values_list("permission__code", flat=True)
        return frozenset(codes)
