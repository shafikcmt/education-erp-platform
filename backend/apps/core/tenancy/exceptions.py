"""Tenant-isolation errors (Phase 3 plan §8.1; ADR-042).

All of them derive from :class:`TenantIsolationError`, so callers and monitoring can treat any
isolation failure as one class of security event. None of them is ever caught to "fall back"
to unscoped access: they fail closed.
"""


class TenantIsolationError(Exception):
    """Base class for every tenant-isolation failure."""


class InvalidTenantId(TenantIsolationError, ValueError):
    """The value is not a canonical UUIDv7 tenant identifier."""


class TenantContextMissing(TenantIsolationError):
    """Tenant-scoped code ran without a tenant context (fail closed)."""


class TenantContextConflict(TenantIsolationError):
    """An attempt to switch to a different tenant while one is active, or to start platform
    code inside a tenant context."""


class TenantContextNotApplied(TenantIsolationError):
    """A query ran while a tenant context was bound in Python but the current database
    transaction on that connection had not applied it (``tenant_atomic`` not used)."""


class TenantContextLeak(TenantIsolationError):
    """Tenant state outlived its transaction, request or task (detected at a boundary)."""


class TenantMismatch(TenantIsolationError):
    """A tenant-scoped row would be created in, or moved to, a tenant other than the current
    one."""


class PlatformScopeError(TenantIsolationError):
    """``platform_scope`` was misused: unknown or disabled operation, wrong actor kind, missing
    reason, nesting, or a mechanism the operation is not catalogued for."""
