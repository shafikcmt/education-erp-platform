"""``platform_scope`` and the platform operation catalogue (Phase 3 plan §6.3-§6.4; ADR-043).

Platform code that needs tenant-related data runs inside
``platform_scope(operation=..., actor=..., reason=...)``. The scope:

* accepts only catalogued, enabled operation ids (P1-P16);
* re-checks the actor's permission **without cache** (through the configured authorizer, so
  ``core`` never imports ``rbac``);
* refuses to start inside a tenant context, or nested in another platform scope;
* audits start and end (with outcome and affected tenant count) where the catalogue says so
  (through the configured auditor, so ``core`` never imports ``audit``);
* **never** sets a tenant, changes database role, disables RLS or uses ``BYPASSRLS``.

Inside the scope, ``tenant_atomic(t)`` is allowed only for operations catalogued with the
targeted (``T``) or per-tenant iteration (``I``) mechanism; each such transaction is a normal
tenant transaction under RLS.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Literal

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from apps.core.tenancy.context import _PLATFORM_OPERATION, current_tenant
from apps.core.tenancy.exceptions import PlatformScopeError, TenantContextConflict
from apps.core.tenancy.transaction import connections_with_tenant_state

Mechanism = Literal["R", "T", "I", "D"]
ActorKind = Literal["user", "system", "anonymous"]


@dataclass(frozen=True)
class PlatformOperationSpec:
    """One row of the plan §6.3 catalogue."""

    id: str
    title: str
    actor: ActorKind
    mechanisms: frozenset[Mechanism]
    permissions: tuple[str, ...] = ()
    audited: bool = True
    enabled: bool = True
    disabled_reason: str = ""


def _op(
    op_id: str,
    title: str,
    actor: ActorKind,
    mechanisms: str,
    permissions: tuple[str, ...] = (),
    *,
    audited: bool = True,
    disabled_reason: str = "",
) -> PlatformOperationSpec:
    return PlatformOperationSpec(
        id=op_id,
        title=title,
        actor=actor,
        mechanisms=frozenset(mechanisms),  # type: ignore[arg-type]
        permissions=permissions,
        audited=audited,
        enabled=not disabled_reason,
        disabled_reason=disabled_reason,
    )


# Plan §6.3. Permission codes of later milestones are listed now; until they are registered,
# the authorizer raises (fail closed).
CATALOGUE: dict[str, PlatformOperationSpec] = {
    spec.id: spec
    for spec in (
        _op("P1", "Resolve request host to tenant", "anonymous", "D", audited=False),
        _op("P2", "My institutions (own memberships)", "user", "D", audited=False),
        _op(
            "P3",
            "Tenant-host sign-in and membership check",
            "user",
            "",
            disabled_reason="Not a platform operation: runs in the tenant-host transaction.",
        ),
        _op("P4", "Provision a tenant", "user", "RT", ("tenancy.tenant.create",)),
        _op(
            "P5",
            "Tenant registry update, suspension, limits",
            "user",
            "RT",
            (
                "tenancy.tenant.view_any",
                "tenancy.tenant.update_any",
                "tenancy.tenant.suspend",
                "tenancy.limit.override",
            ),
        ),
        _op(
            "P6",
            "Request, end or list own support sessions",
            "user",
            "TD",
            ("tenancy.support_session.request",),
        ),
        _op("P7", "Sync tenant system role copies", "system", "I"),
        _op(
            "P8",
            "Platform dashboard counts",
            "user",
            "R",
            ("tenancy.tenant.view_any",),
            audited=False,
        ),
        _op(
            "P9",
            "Platform account administration (Phase 2)",
            "user",
            "R",
            ("identity.user.deactivate", "identity.mfa.reset", "identity.session.revoke_any"),
        ),
        _op("P10", "Anonymise expired security-event IPs", "system", "RI"),
        _op(
            "P11",
            "Security investigation of a tenant audit log",
            "user",
            "",
            disabled_reason="Only through an approved support session on the tenant host (D3).",
        ),
        _op("P12", "Security email, identity housekeeping, ping", "system", "R", audited=False),
        _op("P13", "Data migrations touching tenant rows", "system", "I"),
        _op("P14", "Cross-tenant isolation monitoring", "system", "R", audited=False),
        _op(
            "P15",
            "Tenant export and purge",
            "user",
            "",
            disabled_reason="Planned for Phase 18; not available in Phase 3.",
        ),
        # Phase 4 (plan §5; ADR-051): billing and entitlements.
        _op(
            "P17",
            "Manage modules, plans, add-ons, prices and feature flags",
            "user",
            "R",
            ("billing.plan.manage", "billing.price.manage", "module_registry.flag.manage"),
        ),
        _op(
            "P18",
            "Change a tenant's plan, add-ons, trial and module overrides",
            "user",
            "RT",
            ("billing.subscription.manage",),
        ),
        _op("P19", "Entitlement and trial expiry sweep", "system", "I"),
        _op(
            "P20",
            "Module catalogue sync",
            "system",
            "R",
            audited=False,
            disabled_reason="Owner-run bootstrap (sync_modules), not a runtime platform scope.",
        ),
        _op(
            "P21",
            "Preset catalogue sync",
            "system",
            "R",
            audited=False,
            disabled_reason="Owner-run bootstrap (sync_presets), not a runtime platform scope.",
        ),
        _op(
            "P22",
            "Preset pinning at provisioning",
            "user",
            "T",
            disabled_reason="Runs inside P4 and the tenant transaction; no separate scope.",
        ),
        _op(
            "P23",
            "Self-service sign-up",
            "user",
            "RT",
            disabled_reason="Planned for Phase 5 M7, behind a feature flag that is off (ADR-060).",
        ),
        _op("P24", "Workflow SLA sweep", "system", "I"),
        _op(
            "P16",
            "Incident break-glass",
            "user",
            "",
            disabled_reason="Not in Phase 3 (D6): needs a new ADR and explicit owner approval.",
        ),
    )
}


class _SystemActor:
    """The actor for scheduled tasks and migrations."""

    is_authenticated = False
    is_active = True
    pk = None

    def __repr__(self) -> str:
        return "SYSTEM"


SYSTEM = _SystemActor()

_REASON_MIN, _REASON_MAX = 3, 200


@dataclass
class PlatformOperation:
    """Handle yielded by ``platform_scope``."""

    spec: PlatformOperationSpec
    actor: Any
    reason: str
    permission: str | None
    tenant_ids: set[uuid.UUID] = field(default_factory=set)
    operation_id: str = field(init=False, default="")

    def __post_init__(self) -> None:
        self.operation_id = self.spec.id

    def allows_tenant_transactions(self) -> bool:
        return bool(self.spec.mechanisms & {"T", "I"})

    def touch(self, tenant_id: uuid.UUID) -> None:
        if "I" not in self.spec.mechanisms and self.tenant_ids and tenant_id not in self.tenant_ids:
            raise PlatformScopeError(
                f"{self.spec.id} targets one tenant; iterating over tenants needs mechanism I."
            )
        self.tenant_ids.add(tenant_id)


def _hook(setting: str) -> Callable[..., Any]:
    path = getattr(settings, setting, "")
    if not path:
        raise ImproperlyConfigured(f"{setting} must be configured for platform_scope.")
    return import_string(path)  # type: ignore[no-any-return]


def _validate(
    operation: str, actor: Any, reason: str, permission: str | None
) -> tuple[PlatformOperationSpec, str | None, str]:
    spec = CATALOGUE.get(operation)
    if spec is None:
        raise PlatformScopeError(f"Unknown platform operation {operation!r}.")
    if not spec.enabled:
        raise PlatformScopeError(
            f"Platform operation {spec.id} is disabled: {spec.disabled_reason}"
        )
    cleaned = (reason or "").strip()
    if not _REASON_MIN <= len(cleaned) <= _REASON_MAX:
        raise PlatformScopeError("A reason of 3 to 200 characters is required.")
    if spec.actor == "system":
        if actor is not SYSTEM:
            raise PlatformScopeError(f"{spec.id} runs only as the system actor.")
        return spec, None, cleaned
    if actor is SYSTEM:
        raise PlatformScopeError(f"{spec.id} must run for a user, not the system actor.")
    if spec.actor == "anonymous":
        return spec, None, cleaned
    if actor is None or not getattr(actor, "is_authenticated", False):
        raise PlatformScopeError(f"{spec.id} needs an authenticated user.")
    if not spec.permissions:
        return spec, None, cleaned  # own-account operation (P2)
    if permission is None:
        if len(spec.permissions) != 1:
            raise PlatformScopeError(
                f"{spec.id} covers several actions; pass the exact permission for this one."
            )
        permission = spec.permissions[0]
    elif permission not in spec.permissions:
        raise PlatformScopeError(f"{permission!r} is not catalogued for {spec.id}.")
    return spec, permission, cleaned


@contextmanager
def platform_scope(
    *, operation: str, actor: Any, reason: str, permission: str | None = None
) -> Iterator[PlatformOperation]:
    """Run catalogued platform code (see module docstring)."""
    if current_tenant() is not None or connections_with_tenant_state():
        raise TenantContextConflict("platform_scope can't start inside a tenant context.")
    if _PLATFORM_OPERATION.get() is not None:
        raise PlatformScopeError("platform_scope can't be nested.")
    spec, permission, cleaned = _validate(operation, actor, reason, permission)
    if permission is not None:
        _hook("TENANCY_PLATFORM_AUTHORIZER")(actor, permission)  # uncached; raises if denied
    auditor = _hook("TENANCY_PLATFORM_AUDITOR") if spec.audited else None
    handle = PlatformOperation(spec=spec, actor=actor, reason=cleaned, permission=permission)
    if auditor is not None:
        auditor(handle, stage="started", succeeded=True)
    token = _PLATFORM_OPERATION.set(handle)
    succeeded = False
    try:
        yield handle
        succeeded = True
    finally:
        _PLATFORM_OPERATION.reset(token)
        if auditor is not None:
            auditor(handle, stage="completed", succeeded=succeeded)
