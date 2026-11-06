"""Invalidate cached permission sets on any authorization data change (plan §4.4)."""

from typing import Any

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.rbac.engine import bump_cache_version
from apps.rbac.models import Permission, PlatformRoleAssignment, Role, RolePermission


@receiver([post_save, post_delete], sender=Permission)
@receiver([post_save, post_delete], sender=Role)
@receiver([post_save, post_delete], sender=RolePermission)
@receiver([post_save, post_delete], sender=PlatformRoleAssignment)
def _invalidate(**_: Any) -> None:
    bump_cache_version()
