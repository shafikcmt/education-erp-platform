"""Institution and campus limits (Phase 3 M2; ADR-010, Q12).

Limits live on the tenant registry row (defaults 1 institution / 3 campuses from
``TENANT_DEFAULT_LIMITS``; Super Admin overrides are recorded on the row; Phase 4 plans take
over as the source). Creation code calls :func:`assert_capacity` **inside the tenant
transaction that creates the row**: it locks the tenant's registry row first, so concurrent
creations are serialised and can never exceed the limit (plan §8.4: lock order tenant →
institution → campus).

Archived institutions and campuses do not count towards the limit.
"""

from __future__ import annotations

from typing import Literal

from django.core.exceptions import PermissionDenied

from apps.core.tenancy import require_tenant
from apps.core.tenancy.transaction import applied_tenant_id
from apps.tenancy.models import Campus, Institution, Tenant
from apps.tenancy.rules import LIMIT_KEYS, default_limits

LimitKind = Literal["institution", "campus"]
_KEY: dict[str, str] = {"institution": "max_institutions", "campus": "max_campuses"}


class LimitExceeded(PermissionDenied):
    code = "limit_exceeded"

    def __init__(self, kind: str, limit: int) -> None:
        super().__init__(f"The tenant's {kind} limit ({limit}) is reached.")
        self.kind = kind
        self.limit = limit


def effective_limits(tenant: Tenant) -> dict[str, int]:
    limits = default_limits()
    stored = tenant.limits if isinstance(tenant.limits, dict) else {}
    for key in LIMIT_KEYS:
        if isinstance(stored.get(key), int) and not isinstance(stored.get(key), bool):
            limits[key] = int(stored[key])
    return limits


def assert_capacity(kind: LimitKind) -> Tenant:
    """Lock the current tenant's registry row and refuse if ``kind`` is at its limit.

    Must run inside ``tenant_atomic`` (the lock lasts until that transaction ends).
    """
    from django.db import connection

    ctx = require_tenant()
    if applied_tenant_id(connection) != ctx.id:
        raise PermissionDenied("assert_capacity must run inside tenant_atomic().")
    tenant = Tenant.objects.select_for_update().get(pk=ctx.id)
    limit = effective_limits(tenant)[_KEY[kind]]
    model = Institution if kind == "institution" else Campus
    if model.objects.filter(archived_at__isnull=True).count() >= limit:
        raise LimitExceeded(kind, limit)
    return tenant
