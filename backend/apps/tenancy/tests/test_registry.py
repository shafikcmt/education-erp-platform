"""Tenant registry (Phase 3 M2): slug rules, lifecycle, limits defaults, self-scoped RLS,
tombstones (plan §4.1, §4.3, §5.1, §10.4; Q12)."""

from __future__ import annotations

import itertools
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.utils import ProgrammingError

from apps.core.ids import new_id
from apps.core.tenancy import tenant_atomic
from apps.tenancy.models import Tenant
from apps.tenancy.rules import (
    RESERVED_SLUGS,
    TRANSITIONS,
    InvalidSlug,
    InvalidStatusTransition,
    TenantStatus,
    check_transition,
    validate_slug,
)

pytestmark = pytest.mark.django_db
STATUSES = [c for c, _ in TenantStatus.CHOICES]


def _raw(sql: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return list(cursor.fetchall()) if cursor.description else []


# --------------------------------------------------------------------------- slugs
@pytest.mark.parametrize("slug", ["abc", "acme-school", "a1b", "x" * 32, "madrasa-2026"])
def test_valid_slugs(slug):
    assert validate_slug(slug) == slug


@pytest.mark.parametrize(
    "slug", ["ab", "x" * 33, "1abc", "-abc", "abc-", "Abc", "ab_c", "ab c", "a--b", "", "ab.c"]
)
def test_invalid_slugs(slug):
    with pytest.raises(InvalidSlug):
        validate_slug(slug)


@pytest.mark.parametrize("slug", sorted(s for s in RESERVED_SLUGS if len(s) >= 3))
def test_reserved_slugs_are_refused(slug):
    """Format-valid reserved names fail as reserved (shorter ones: see the M2 decision tests)."""
    with pytest.raises(InvalidSlug, match="reserved"):
        validate_slug(slug)


def test_database_rejects_invalid_and_reserved_slugs_too():
    for bad in ("Bad", "admin", "a--b"):
        with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO tenancy_tenant (id, created_at, updated_at, slug, name, status, "
                "default_locale, locales, timezone, currency, country, data_region, limits, "
                "limits_override_reason, settings, branding) VALUES (%s, now(), now(), %s, 'x', "
                "'active', 'en', '{}', 'UTC', 'USD', '', '', '{}', '', '{}', '{}')",
                [new_id(), bad],
            )


def test_slugs_are_unique_immutable_and_tombstoned(tenant_factory):
    ctx = tenant_factory(slug="acme")
    with pytest.raises(IntegrityError), transaction.atomic():
        Tenant.objects.create(slug="acme", name="Again")
    tenant = Tenant.objects.get(pk=ctx.id)
    tenant.slug = "acme-renamed"
    with pytest.raises(InvalidSlug, match="never change"):
        tenant.save()
    with pytest.raises(IntegrityError, match="slug is immutable"), transaction.atomic():
        _raw("UPDATE tenancy_tenant SET slug = 'acme-renamed' WHERE id = %s", [ctx.id])
    # Deleted tenants keep their row: the runtime role can't delete registry rows at all.
    with pytest.raises(ProgrammingError, match="permission denied"), transaction.atomic():
        _raw("DELETE FROM tenancy_tenant WHERE id = %s", [ctx.id])


# --------------------------------------------------------------------------- lifecycle
def test_python_and_database_transition_rules_agree(tenant_factory):
    """Every (from, to) pair: the guard trigger accepts exactly the TRANSITIONS table."""
    for old, new in itertools.product(STATUSES, STATUSES):
        if old == new:
            continue
        ctx = tenant_factory(status=old)
        allowed = new in TRANSITIONS[old]
        error = ""
        try:
            with transaction.atomic():
                _raw("UPDATE tenancy_tenant SET status = %s WHERE id = %s", [new, ctx.id])
        except IntegrityError as exc:
            error = str(exc)
        db_ok = not error
        assert db_ok or "invalid tenant status transition" in error
        assert db_ok is allowed, (old, new)
        if allowed:
            check_transition(old, new)
        else:
            with pytest.raises(InvalidStatusTransition):
                check_transition(old, new)


def test_model_enforces_transitions_and_deleted_is_terminal(tenant_factory):
    tenant = Tenant.objects.get(pk=tenant_factory(status=TenantStatus.PROVISIONING).id)
    tenant.status = TenantStatus.SUSPENDED
    with pytest.raises(InvalidStatusTransition):
        tenant.save()
    for step in (TenantStatus.ACTIVE, TenantStatus.SUSPENDED, TenantStatus.OFFBOARDING):
        tenant.status = step
        tenant.save()
    tenant.status = TenantStatus.DELETED
    tenant.save()
    for anything in STATUSES:
        if anything != TenantStatus.DELETED:
            tenant.status = anything
            with pytest.raises(ValidationError):
                tenant.save()


def test_new_tenants_get_default_limits_and_settings(settings):
    tenant = Tenant.objects.create(slug="defaults", name="Defaults")
    assert tenant.status == TenantStatus.PROVISIONING
    assert tenant.limits == {"max_institutions": 1, "max_campuses": 3}
    assert tenant.settings == {"support_access_requires_approval": True}
    settings.TENANT_DEFAULT_LIMITS = {"max_institutions": 2, "max_campuses": 5}
    assert Tenant.objects.create(slug="defaults-two", name="X").limits == {
        "max_institutions": 2,
        "max_campuses": 5,
    }
    ctx = tenant.as_context()
    assert (ctx.id, ctx.slug, ctx.status) == (tenant.id, "defaults", "provisioning")


# --------------------------------------------------------------------------- self-scoped RLS
def test_registry_is_self_scoped(tenant_factory):
    a, b = tenant_factory(), tenant_factory()
    ids = {row[0] for row in _raw("SELECT id FROM tenancy_tenant")}
    assert {a.id, b.id} <= ids  # platform (no context) sees the whole registry
    with tenant_atomic(a):
        assert _raw("SELECT id FROM tenancy_tenant") == [(a.id,)]
        assert list(Tenant.objects.values_list("id", flat=True)) == [a.id]
        assert (
            _raw("UPDATE tenancy_tenant SET name = 'hijack' WHERE id = %s RETURNING id", [b.id])
            == []
        )
        with pytest.raises(DatabaseError, match="row-level security"), transaction.atomic():
            Tenant.objects.create(slug="sneaky", name="Sneaky")
    assert Tenant.objects.get(pk=b.id).name != "hijack"


def test_registry_policies_have_the_self_scoped_shape():
    rows = _raw(
        "SELECT polname, polcmd::text, pg_get_expr(polqual, polrelid), "
        "pg_get_expr(polwithcheck, polrelid) FROM pg_policy "
        "WHERE polrelid = 'tenancy_tenant'::regclass ORDER BY polname"
    )
    assert {r[0] for r in rows} == {
        f"tenant_isolation_{c}" for c in ("select", "insert", "update", "delete")
    }
    for _, _, using, check in rows:
        for expr in filter(None, (using, check)):
            assert "IS NULL) OR (id =" in expr and "app_tenant_id()" in expr
    forced = _raw(
        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
        "WHERE oid = 'tenancy_tenant'::regclass"
    )
    assert forced == [(True, True)]


# --------------------------------------------------------------------------- M2 review decisions
ORIGINAL_RESERVED = {
    "admin", "api", "app", "assets", "auth", "billing", "blog", "cdn", "dashboard", "dev",
    "docs", "ftp", "help", "imap", "login", "mail", "media", "ns1", "ns2", "platform", "pop",
    "portal", "root", "security", "smtp", "sso", "staging", "static", "status", "support",
    "system", "test", "www",
}  # fmt: skip
ADDED_RESERVED = {
    "account", "accounts", "my", "id", "oauth", "oidc", "signup", "register", "onboarding",
    "files", "storage", "uploads", "s3", "pay", "payments", "checkout", "demo", "sandbox",
    "preview", "beta", "internal", "metrics", "monitoring", "webmail", "email", "autodiscover",
    "autoconfig", "mta-sts", "postmaster", "abuse", "noreply", "localhost", "mobile", "tenant",
    "tenants",
}  # fmt: skip


def test_reserved_list_is_the_approved_68_names():
    assert len(ORIGINAL_RESERVED) == 33 and len(ADDED_RESERVED) == 35
    assert RESERVED_SLUGS == ORIGINAL_RESERVED | ADDED_RESERVED
    assert len(RESERVED_SLUGS) == 68
    assert all(slug == slug.lower().strip() for slug in RESERVED_SLUGS)


@pytest.mark.parametrize("slug", sorted(ADDED_RESERVED))
def test_every_newly_reserved_slug_is_refused(slug):
    with pytest.raises(InvalidSlug) as exc:
        validate_slug(slug)
    # Format-valid names fail as reserved; my/id/s3 already fail the 3-character minimum.
    expected = "invalid_slug" if len(slug) < 3 else "reserved_slug"
    assert exc.value.code == expected


@pytest.mark.parametrize("slug", sorted(s for s in ADDED_RESERVED if len(s) >= 3))
def test_database_check_refuses_newly_reserved_slugs(slug):
    with pytest.raises(IntegrityError, match="tenancy_tenant_slug_valid"):
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO tenancy_tenant (id, created_at, updated_at, slug, name, status, "
                "default_locale, locales, timezone, currency, country, data_region, limits, "
                "limits_override_reason, settings, branding) VALUES (%s, now(), now(), %s, 'x', "
                "'active', 'en', '{}', 'UTC', 'USD', '', '', '{}', '', '{}', '{}')",
                [new_id(), slug],
            )


def test_offboarding_cannot_reactivate_directly(tenant_factory):
    """Owner decision: offboarding -> suspended -> active is the only way back."""
    assert TRANSITIONS[TenantStatus.OFFBOARDING] == {TenantStatus.SUSPENDED, TenantStatus.DELETED}
    assert {s for s, targets in TRANSITIONS.items() if TenantStatus.ACTIVE in targets} == {
        TenantStatus.PROVISIONING,
        TenantStatus.SUSPENDED,
    }
    ctx = tenant_factory(status=TenantStatus.OFFBOARDING)
    with pytest.raises(IntegrityError, match="offboarding -> active"), transaction.atomic():
        _raw("UPDATE tenancy_tenant SET status = 'active' WHERE id = %s", [ctx.id])
    tenant = Tenant.objects.get(pk=ctx.id)
    tenant.status = TenantStatus.ACTIVE
    with pytest.raises(InvalidStatusTransition):
        tenant.save()
    tenant.status = TenantStatus.SUSPENDED
    tenant.save()
    tenant.status = TenantStatus.ACTIVE
    tenant.save()
    assert Tenant.objects.get(pk=ctx.id).status == TenantStatus.ACTIVE
