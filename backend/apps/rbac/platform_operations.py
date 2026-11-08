"""Authorizer for ``apps.core.tenancy.platform.platform_scope`` (ADR-043).

Configured as ``settings.TENANCY_PLATFORM_AUTHORIZER`` so that ``core`` never imports ``rbac``.
The check is **uncached** and against the platform target: platform permissions never apply to
tenant targets (ADR-033), and a revoked platform role takes effect immediately.
"""

from typing import Any

from apps.rbac.engine import PLATFORM, require_perm


def authorize_platform_operation(actor: Any, permission: str) -> None:
    """Raise ``PermissionDenied`` (or ``UnknownPermissionError``) unless ``actor`` holds it."""
    require_perm(actor, permission, target=PLATFORM, use_cache=False)
