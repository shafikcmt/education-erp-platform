"""Review H3: runtime processes refuse owner/superuser DB credentials (in-process unit tests;
the production settings module is also exercised end-to-end in test_settings.py)."""

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.core.config_guards import (
    assert_host_configuration,
    assert_no_persistent_connections,
    assert_runtime_has_no_owner_credentials,
    is_placeholder_domain,
)

OWNERS = {"erp_owner", "postgres"}


@pytest.mark.parametrize(
    "environ",
    [
        {"DATABASE_MIGRATION_URL": "postgres://erp_owner:x@db/erp"},
        {"ERP_OWNER_PASSWORD": "x"},
        {"POSTGRES_PASSWORD": "x"},
    ],
)
def test_owner_credentials_in_runtime_env_are_refused(environ):
    with pytest.raises(ImproperlyConfigured, match="must not receive"):
        assert_runtime_has_no_owner_credentials(
            environ, database_user="erp_app", owner_roles=OWNERS
        )


@pytest.mark.parametrize("user", ["erp_owner", "postgres"])
def test_privileged_database_user_is_refused(user):
    with pytest.raises(ImproperlyConfigured, match="privileged database role"):
        assert_runtime_has_no_owner_credentials({}, database_user=user, owner_roles=OWNERS)


def test_runtime_role_and_migrate_process_are_allowed():
    assert_runtime_has_no_owner_credentials({}, database_user="erp_app", owner_roles=OWNERS)
    assert_runtime_has_no_owner_credentials(
        {"ERP_PROCESS_ROLE": "migrate", "DATABASE_MIGRATION_URL": "postgres://erp_owner:x@db/erp"},
        database_user="erp_owner",
        owner_roles=OWNERS,
    )


# --------------------------------------------------------------------------- host policy (M3)
RESERVED = {"admin", "api", "www"}


def _hosts(**overrides):
    config = {
        "platform_hosts": ["admin.schools.io"],
        "allowed_hosts": ["admin.schools.io", ".schools.io"],
        "tenant_hosts_enabled": True,
        "tenant_base_domain": "schools.io",
        "reserved_labels": RESERVED,
        "production": True,
    }
    assert_host_configuration(**{**config, **overrides})


def test_valid_production_host_configuration_is_accepted():
    _hosts()
    _hosts(tenant_hosts_enabled=False, tenant_base_domain="")
    # Disabled tenant hosts never need a real domain (D1: the default state).
    _hosts(tenant_hosts_enabled=False, tenant_base_domain="localhost")


@pytest.mark.parametrize(
    "domain",
    [
        "",
        "localhost",
        "tenants.test",
        "erp.example",
        "x.invalid",
        "campus.local",
        "example.com",
        "erp.example.org",
        "sub.localhost",
        "nodots",
        "Bad_Domain.io",
    ],
)
def test_tenant_hosts_need_a_real_base_domain_in_production(domain):
    with pytest.raises(ImproperlyConfigured, match=r"TENANT_BASE_DOMAIN|TENANT_HOSTS_ENABLED"):
        _hosts(tenant_base_domain=domain, allowed_hosts=["admin.schools.io", "." + domain])


def test_placeholder_domains_are_fine_outside_production():
    _hosts(
        production=False,
        platform_hosts=["localhost", "api"],
        tenant_base_domain="localhost",
        allowed_hosts=[".localhost"],
    )


def test_production_requires_allowed_platform_hosts_and_covered_tenant_hosts():
    with pytest.raises(ImproperlyConfigured, match="PLATFORM_HOSTS must be set"):
        _hosts(platform_hosts=[])
    with pytest.raises(ImproperlyConfigured, match="not in DJANGO_ALLOWED_HOSTS"):
        _hosts(allowed_hosts=[".schools.io.other"])
    with pytest.raises(ImproperlyConfigured, match="must cover the tenant hosts"):
        _hosts(allowed_hosts=["admin.schools.io"])


@pytest.mark.parametrize("production", [True, False])
def test_platform_host_under_the_tenant_domain_needs_a_reserved_label(production):
    with pytest.raises(ImproperlyConfigured, match="could be a tenant host"):
        _hosts(platform_hosts=["acme.schools.io"], production=production)
    _hosts(platform_hosts=["www.schools.io"], production=production)


@pytest.mark.parametrize("host", ["Admin.schools.io", "admin.schools.io:443", " admin.schools.io"])
def test_platform_hosts_must_be_normalised(host):
    with pytest.raises(ImproperlyConfigured, match="lower-case host names without a port"):
        _hosts(platform_hosts=[host])


@pytest.mark.parametrize(
    ("domain", "placeholder"),
    [("localhost", True), ("a.test", True), ("example.org", True), ("schools.io", False)],
)
def test_placeholder_detection(domain, placeholder):
    assert is_placeholder_domain(domain) is placeholder


def test_production_refuses_persistent_connections():
    assert_no_persistent_connections({"default": {"CONN_MAX_AGE": 0}, "audit_durable": {}})
    with pytest.raises(ImproperlyConfigured, match="CONN_MAX_AGE = 0"):
        assert_no_persistent_connections(
            {"default": {"CONN_MAX_AGE": 0}, "x": {"CONN_MAX_AGE": 60}}
        )
    with pytest.raises(ImproperlyConfigured, match="CONN_MAX_AGE = 0"):
        assert_no_persistent_connections({"default": {"CONN_MAX_AGE": None}})
