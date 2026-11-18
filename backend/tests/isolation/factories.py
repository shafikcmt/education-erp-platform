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


def seed_tenant_roles(tenant: TenantContext) -> None:
    """Give the tenant its read-only system role copies (done by provisioning from M8)."""
    from apps.rbac.tenant_roles import sync_system_copies

    with tenant_atomic(tenant):
        sync_system_copies(tenant.id)


def grant_role(
    tenant: TenantContext,
    user: Any,
    template_code: str,
    *,
    institution: Any = None,
    campus: Any = None,
) -> Any:
    """Make ``user`` an active member holding the system copy of ``template_code`` in a scope
    (tenant scope by default). No actor is authorised: this is test set-up."""
    from apps.rbac.tenant_roles import system_role
    from apps.tenancy.services.assignments import create_assignment

    scope = (
        "campus" if campus is not None else "institution" if institution is not None else "tenant"
    )
    with tenant_atomic(tenant):
        membership = Membership.objects.filter(user=user).first() or Membership.objects.create(
            user=user, status="active", joined_at=timezone.now()
        )
        return create_assignment(
            membership=membership,
            role=system_role(tenant.id, template_code),
            scope_type=scope,
            institution=institution,
            campus=campus,
        )


def delete_tenants_as_owner(owner_dsn: dict[str, Any], *tenants: TenantContext) -> None:
    with psycopg.connect(**owner_dsn, autocommit=True) as conn:
        conn.execute("DELETE FROM tenancy_tenant WHERE id = ANY(%s)", [[t.id for t in tenants]])


def _delete_tenant_rows(*tenants: TenantContext) -> None:
    def run() -> None:
        from apps.rbac.models import Role, RoleAssignment, RolePermission
        from apps.tenancy.models import Campus, Institution, Invitation

        for tenant in tenants:
            with tenant_atomic(tenant):
                RoleAssignment.objects.all().delete()
                Invitation.objects.all().delete()
                Membership.objects.all().delete()
                Campus.objects.all().delete()
                Institution.objects.all().delete()
                TenantDomain.objects.all().delete()
                RolePermission.objects.filter(role__tenant_id=tenant.id).delete()
                Role.objects.filter(tenant_id=tenant.id).delete()

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
