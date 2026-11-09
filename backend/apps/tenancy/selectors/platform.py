"""The **only** callers of the tenancy ``SECURITY DEFINER`` functions (plan §7; ADR-043).

Each wrapper runs only inside the ``platform_scope`` operation it is catalogued for:

* F1 :func:`resolve_host` (P1, anonymous): host → tenant before any context exists;
* F2 :func:`memberships_of` (P2, own account): "My institutions";
* F3 :func:`support_sessions_of` (P6): a staff member's own support sessions.

``platform_scope`` already refuses to start inside a tenant context. The wrappers take the user
from the scope's actor (never a caller-supplied id), validate input before calling SQL, and
return only the documented columns. A static test forbids any other caller.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from django.db import connection

from apps.core.tenancy.context import active_platform_operation
from apps.core.tenancy.exceptions import PlatformScopeError
from apps.tenancy.rules import is_valid_domain


@dataclass(frozen=True)
class HostResolution:
    tenant_id: uuid.UUID
    status: str


@dataclass(frozen=True)
class MembershipSummary:
    tenant_id: uuid.UUID
    slug: str
    name: str
    tenant_status: str
    membership_status: str


@dataclass(frozen=True)
class SupportSessionSummary:
    session_id: uuid.UUID
    tenant_id: uuid.UUID
    tenant_slug: str
    status: str
    starts_at: datetime | None
    ends_at: datetime | None


def _require_operation(operation_id: str) -> object:
    operation = active_platform_operation()
    if operation is None or operation.operation_id != operation_id:
        raise PlatformScopeError(
            f"Only callable inside platform_scope(operation={operation_id!r})."
        )
    return operation


def _actor_id(operation: object) -> uuid.UUID:
    actor = getattr(operation, "actor", None)
    if actor is None or not getattr(actor, "is_authenticated", False):
        raise PlatformScopeError("An authenticated actor is required.")
    return uuid.UUID(str(actor.pk))


def resolve_host(host: str) -> HostResolution | None:
    """F1. ``None`` for invalid, unknown, unverified, provisioning or deleted hosts alike."""
    _require_operation("P1")
    if not is_valid_domain(host):
        return None
    with connection.cursor() as cursor:
        cursor.execute("SELECT tenant_id, status FROM public.tenancy_resolve_host(%s)", [host])
        row = cursor.fetchone()
    return HostResolution(tenant_id=row[0], status=row[1]) if row else None


def memberships_of() -> list[MembershipSummary]:
    """F2. The scope actor's own memberships (invited/active/suspended, resolvable tenants)."""
    user_id = _actor_id(_require_operation("P2"))
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tenant_id, slug, name, tenant_status, membership_status "
            "FROM public.tenancy_memberships_of(%s)",
            [user_id],
        )
        rows = cursor.fetchall()
    return [MembershipSummary(*row) for row in rows]


def support_sessions_of() -> list[SupportSessionSummary]:
    """F3. The scope actor's own support sessions across tenants (metadata only)."""
    staff_id = _actor_id(_require_operation("P6"))
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT session_id, tenant_id, tenant_slug, status, starts_at, ends_at "
            "FROM public.tenancy_support_sessions_of(%s)",
            [staff_id],
        )
        rows = cursor.fetchall()
    return [SupportSessionSummary(*row) for row in rows]
