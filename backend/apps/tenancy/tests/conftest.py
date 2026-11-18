"""Shared fixtures of the tenancy tests (Phase 3 M4)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.core.tenancy import tenant_atomic
from apps.rbac.engine import ScopeTarget
from apps.tenancy.models import Campus, Institution
from tests.helpers import make_user
from tests.isolation.factories import grant_role, seed_tenant_roles


@pytest.fixture
def org(tenant_site) -> SimpleNamespace:
    """One tenant with two institutions, three campuses and four members."""
    tenant = tenant_site(slug="acme")
    seed_tenant_roles(tenant)
    with tenant_atomic(tenant):
        north = Institution.objects.create(code="north", name="North", institution_type="school")
        south = Institution.objects.create(code="south", name="South", institution_type="madrasa")
        main = Campus.objects.create(institution=north, code="main", name="Main", is_main=True)
        annex = Campus.objects.create(institution=north, code="annex", name="Annex")
        south_main = Campus.objects.create(
            institution=south, code="main", name="South main", is_main=True
        )
    owner = make_user("owner@example.com").user
    head = make_user("head@example.com").user
    campus_admin = make_user("campus@example.com").user
    teacher = make_user("teacher@example.com").user
    grant_role(tenant, owner, "tenant_owner")
    grant_role(tenant, head, "institution_admin", institution=north)
    grant_role(tenant, campus_admin, "campus_admin", institution=north, campus=main)
    grant_role(tenant, teacher, "teacher", institution=north, campus=main)
    return SimpleNamespace(
        tenant=tenant,
        north=north,
        south=south,
        main=main,
        annex=annex,
        south_main=south_main,
        owner=owner,
        head=head,
        campus_admin=campus_admin,
        teacher=teacher,
        t_tenant=ScopeTarget(tenant.id),
        t_north=ScopeTarget(tenant.id, north.pk),
        t_south=ScopeTarget(tenant.id, south.pk),
        t_main=ScopeTarget(tenant.id, north.pk, main.pk),
        t_annex=ScopeTarget(tenant.id, north.pk, annex.pk),
        t_south_main=ScopeTarget(tenant.id, south.pk, south_main.pk),
    )
