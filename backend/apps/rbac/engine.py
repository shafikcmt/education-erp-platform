"""Scope-aware permission engine with pluggable sources (Phase 2 plan §4.4; ADR-032).

``has_perm(actor, code, target=...)`` unions the grants of every configured
:class:`PermissionSource` for the target scope. Phase 2 configures ``SelfServiceSource`` and
``PlatformRoleSource``; Phase 3 appends ``TenantMembershipSource`` and ``SupportSessionSource``
in ``settings.RBAC_PERMISSION_SOURCES``. Views and services don't change.

Rules:
* Default deny. Unknown codes raise :class:`UnknownPermissionError` (a programming error).
* Platform grants apply **only** to platform targets (``tenant_id is None``): a Super Admin has
  no implicit tenant-data access (owner requirement 4).
* Tenant grants (Phase 3) apply only where the assignment scope **covers** the target
  (tenant ⊇ institution ⊇ campus; never sideways): see :meth:`ScopeGrant.covers`.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.utils.module_loading import import_string

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser


class UnknownPermissionError(LookupError):
    """The permission code is not registered (typo or missing ``sync_permissions``)."""


@dataclass(frozen=True)
class ScopeTarget:
    """Where an action happens. ``PLATFORM`` = no tenant (platform host)."""

    tenant_id: uuid.UUID | None = None
    institution_id: uuid.UUID | None = None
    campus_id: uuid.UUID | None = None

    @property
    def is_platform(self) -> bool:
        return self.tenant_id is None

    def cache_key(self) -> str:
        if self.is_platform:
            return "platform"
        # Tenant-prefixed (CLAUDE.md §10.7).
        return f"t:{self.tenant_id}:{self.institution_id or '-'}:{self.campus_id or '-'}"


PLATFORM = ScopeTarget()


@dataclass(frozen=True)
class ScopeGrant:
    """Scope of a tenant role assignment (Phase 3 ``RoleAssignment``)."""

    tenant_id: uuid.UUID
    institution_id: uuid.UUID | None = None
    campus_id: uuid.UUID | None = None

    def covers(self, target: ScopeTarget) -> bool:
        """Tenant scope covers the whole tenant; institution scope its campuses; campus itself."""
        if target.tenant_id != self.tenant_id:
            return False
        if self.institution_id is not None and target.institution_id != self.institution_id:
            return False
        return not (self.campus_id is not None and target.campus_id != self.campus_id)


@runtime_checkable
class PermissionSource(Protocol):
    def grants(self, actor: AbstractBaseUser, target: ScopeTarget) -> frozenset[str]: ...


@dataclass(frozen=True)
class PermissionInfo:
    code: str
    requires_mfa: bool
    requires_step_up: bool
    is_sensitive: bool


# ------------------------------------------------------------------ catalog and cache versioning
_VERSION_KEY = "perm:version"
_CATALOG_KEY = "perm:catalog"


def cache_version() -> int:
    version = cache.get(_VERSION_KEY)
    if version is None:
        cache.add(_VERSION_KEY, 1, timeout=None)
        version = cache.get(_VERSION_KEY, 1)
    return int(version)


def bump_cache_version() -> None:
    """Invalidate every cached permission set (any role/permission/assignment change)."""
    try:
        cache.incr(_VERSION_KEY)
    except ValueError:
        cache.add(_VERSION_KEY, 2, timeout=None)


def catalog(*, use_cache: bool = True) -> dict[str, PermissionInfo]:
    """Registered, non-deprecated permissions with their flags (from ``rbac_permission``)."""
    key = f"{_CATALOG_KEY}:v{cache_version()}"
    if use_cache:
        cached = cache.get(key)
        if cached is not None:
            return dict(cached)
    from apps.rbac.models import Permission

    rows = Permission.objects.filter(deprecated_at__isnull=True).values_list(
        "code", "requires_mfa", "requires_step_up", "is_sensitive"
    )
    result = {c: PermissionInfo(c, mfa, step, sens) for c, mfa, step, sens in rows}
    cache.set(key, result, timeout=settings.RBAC_CACHE_TTL_SECONDS)
    return result


def permission_info(code: str) -> PermissionInfo:
    info = catalog().get(code) or catalog(use_cache=False).get(code)
    if info is None:
        raise UnknownPermissionError(code)
    return info


# ------------------------------------------------------------------ sources
@lru_cache(maxsize=8)
def _load_sources(paths: tuple[str, ...]) -> tuple[PermissionSource, ...]:
    return tuple(import_string(path)() for path in paths)


def sources() -> tuple[PermissionSource, ...]:
    return _load_sources(tuple(settings.RBAC_PERMISSION_SOURCES))


def _is_active_user(actor: Any) -> bool:
    return bool(actor is not None and actor.is_authenticated and actor.is_active)


def effective_permissions(
    actor: AbstractBaseUser | AnonymousUser | None,
    target: ScopeTarget = PLATFORM,
    *,
    use_cache: bool = True,
    extra_sources: tuple[PermissionSource, ...] = (),
) -> frozenset[str]:
    """Union of all source grants for ``target`` (cached per user + scope, 300 s, versioned)."""
    if not _is_active_user(actor):
        return frozenset()
    assert actor is not None  # noqa: S101 - narrowed by _is_active_user
    key = f"perm:{target.cache_key()}:{actor.pk}:v{cache_version()}"
    if use_cache and not extra_sources:
        cached = cache.get(key)
        if cached is not None:
            return frozenset(cached)
    granted: set[str] = set()
    for source in (*sources(), *extra_sources):
        granted |= source.grants(actor, target)  # type: ignore[arg-type]
    known = catalog(use_cache=use_cache)
    result = frozenset(code for code in granted if code in known)
    if not extra_sources:
        cache.set(key, result, timeout=settings.RBAC_CACHE_TTL_SECONDS)
    return result


# ------------------------------------------------------------------ object policies
ObjectPolicy = Callable[[Any, str, Any, ScopeTarget], bool]
_POLICIES: dict[str, ObjectPolicy] = {}


def register_policy(resource: str, policy: ObjectPolicy) -> None:
    """Register an object-level policy for ``"<app_label>.<model_name>"`` (Phase 7 hook)."""
    _POLICIES[resource] = policy


def _policy_for(obj: Any) -> ObjectPolicy | None:
    meta = getattr(obj, "_meta", None)
    if meta is None:
        return None
    return _POLICIES.get(f"{meta.app_label}.{meta.model_name}")


# ------------------------------------------------------------------ public API
def has_perm(
    actor: AbstractBaseUser | AnonymousUser | None,
    code: str,
    *,
    target: ScopeTarget = PLATFORM,
    obj: Any = None,
    use_cache: bool = True,
    extra_sources: tuple[PermissionSource, ...] = (),
) -> bool:
    permission_info(code)  # raises UnknownPermissionError
    perms = effective_permissions(actor, target, use_cache=use_cache, extra_sources=extra_sources)
    if code not in perms:
        return False
    policy = _policy_for(obj) if obj is not None else None
    return policy(actor, code, obj, target) if policy else True


def require_perm(
    actor: AbstractBaseUser | AnonymousUser | None,
    code: str,
    *,
    target: ScopeTarget = PLATFORM,
    obj: Any = None,
    use_cache: bool = True,
) -> None:
    """Service-layer guard (defense in depth): raise ``PermissionDenied`` unless allowed."""
    if not has_perm(actor, code, target=target, obj=obj, use_cache=use_cache):
        raise PermissionDenied(code)


def user_requires_mfa(actor: AbstractBaseUser, *, use_cache: bool = True) -> bool:
    """Privileged account (ADR-035): any effective permission flagged ``requires_mfa``, or any
    platform role (all platform roles require MFA, even ones whose Phase 2 permission set is
    empty, such as ``platform_billing``)."""
    if not _is_active_user(actor):
        return False
    known = catalog(use_cache=use_cache)
    if any(known[c].requires_mfa for c in effective_permissions(actor, use_cache=use_cache)):
        return True
    from apps.rbac.models import PlatformRoleAssignment

    return PlatformRoleAssignment.objects.filter(user_id=actor.pk).exists()
