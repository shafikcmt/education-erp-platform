"""Tenant factories for isolation tests (Phase 3 M2).

``TenantScopedModel.tenant`` is a real foreign key to the registry, so tenant-scoped rows need
an existing tenant. ``make_tenant`` creates one in the current transaction (the test
transaction on the main thread). ``committed_tenants`` creates committed tenants for tests that
run real transactions in worker threads; the runtime role may not delete registry rows
(tombstones), so cleanup uses the owner connection.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg

from apps.core.tenancy import TenantContext
from apps.tenancy.models import Tenant
from apps.tenancy.rules import TenantStatus
from tests.isolation.threads import delete_probe_rows, in_thread


def make_tenant(*, slug: str | None = None, status: str = TenantStatus.ACTIVE) -> TenantContext:
    slug = slug or f"t{uuid.uuid4().hex[:12]}"
    return Tenant.objects.create(slug=slug, name=slug.upper(), status=status).as_context()


def delete_tenants_as_owner(owner_dsn: dict[str, Any], *tenants: TenantContext) -> None:
    with psycopg.connect(**owner_dsn, autocommit=True) as conn:
        conn.execute("DELETE FROM tenancy_tenant WHERE id = ANY(%s)", [[t.id for t in tenants]])


@contextmanager
def committed_tenants(owner_dsn: dict[str, Any], count: int) -> Iterator[list[TenantContext]]:
    tenants = in_thread(lambda: [make_tenant() for _ in range(count)])
    try:
        yield tenants
    finally:
        delete_probe_rows(*tenants)
        delete_tenants_as_owner(owner_dsn, *tenants)
