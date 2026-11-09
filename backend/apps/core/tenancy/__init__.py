"""Tenant context primitives (Phase 3 M1; ADR-009, ADR-042, ADR-043).

Public API:

* :class:`TenantContext`, :func:`current_tenant`, :func:`require_tenant`, :func:`bind_tenant`,
  :func:`validate_tenant_id`;
* :func:`tenant_atomic` (the only sanctioned way to open a tenant transaction);
* :class:`TenantScopedModel` / :class:`TenantManager` (import from ``apps.core.tenancy.models``
  to avoid loading models before the app registry is ready);
* :func:`platform_scope` and :data:`SYSTEM` (``apps.core.tenancy.platform``);
* the errors in :mod:`apps.core.tenancy.exceptions`.
"""

from apps.core.tenancy.context import (
    TenantContext,
    bind_tenant,
    current_tenant,
    require_tenant,
    validate_tenant_id,
)
from apps.core.tenancy.exceptions import (
    InvalidTenantId,
    PlatformScopeError,
    TenantContextConflict,
    TenantContextLeak,
    TenantContextMissing,
    TenantContextNotApplied,
    TenantIsolationError,
    TenantMismatch,
)
from apps.core.tenancy.transaction import tenant_atomic

__all__ = [
    "InvalidTenantId",
    "PlatformScopeError",
    "TenantContext",
    "TenantContextConflict",
    "TenantContextLeak",
    "TenantContextMissing",
    "TenantContextNotApplied",
    "TenantIsolationError",
    "TenantMismatch",
    "bind_tenant",
    "current_tenant",
    "require_tenant",
    "tenant_atomic",
    "validate_tenant_id",
]
