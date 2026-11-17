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
from django.conf import settings
from django.utils import timezone

from apps.core.tenancy import TenantContext, tenant_atomic
from apps.tenancy.models import Membership, Tenant, TenantDomain
from apps.tenancy.rules import TenantStatus
from tests.isolation.threads import delete_probe_rows, in_thread


def make_tenant(*, slug: str | None = None, status: str = TenantStatus.ACTIVE) -> TenantContext:
    slug = slug or f"t{uuid.uuid4().hex[:12]}"
    return Tenant.objects.create(slug=slug, name=slug.upper(), status=status).as_context()


def tenant_host(tenant: TenantContext | str) -> str:
    """The test host of a tenant: ``{slug}.tenants.test`` (settings ``TENANT_BASE_DOMAIN``)."""
    slug = tenant if isinstance(tenant, str) else tenant.slug
    return f"{slug}.{settings.TENANT_BASE_DOMAIN}"


def make_tenant_site(
    *, slug: str | None = None, status: str = TenantStatus.ACTIVE, verified: bool = True
) -> TenantContext:
    """A tenant with its (verified) subdomain row, i.e. resolvable by F1."""
    ctx = make_tenant(slug=slug, status=status)
    with tenant_atomic(ctx):
        TenantDomain.objects.create(
            domain=tenant_host(ctx),
            is_primary=True,
            verified_at=timezone.now() if verified else None,
        )
    return ctx


def add_member(tenant: TenantContext, user: Any, *, status: str = "active") -> Membership:
    with tenant_atomic(tenant):
        return Membership.objects.create(user=user, status=status)


def delete_tenants_as_owner(owner_dsn: dict[str, Any], *tenants: TenantContext) -> None:
    with psycopg.connect(**owner_dsn, autocommit=True) as conn:
        conn.execute("DELETE FROM tenancy_tenant WHERE id = ANY(%s)", [[t.id for t in tenants]])


def _delete_tenant_rows(*tenants: TenantContext) -> None:
    def run() -> None:
        for tenant in tenants:
            with tenant_atomic(tenant):
                Membership.objects.all().delete()
                TenantDomain.objects.all().delete()

    in_thread(run)


@contextmanager
def committed_tenants(
    owner_dsn: dict[str, Any], count: int, *, sites: bool = False
) -> Iterator[list[TenantContext]]:
    """Committed tenants (``sites=True``: with a verified domain, resolvable by F1)."""
    make = make_tenant_site if sites else make_tenant
    tenants = in_thread(lambda: [make() for _ in range(count)])
    try:
        yield tenants
    finally:
        delete_probe_rows(*tenants)
        _delete_tenant_rows(*tenants)
        delete_tenants_as_owner(owner_dsn, *tenants)
