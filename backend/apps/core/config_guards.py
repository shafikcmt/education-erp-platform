"""Startup guards for deployment configuration (security review H3).

Runtime processes (API, Celery worker/beat) must never hold database owner or superuser
credentials: the owner role can disable the audit triggers. Only the one-shot migration/ops
process, marked ``ERP_PROCESS_ROLE=migrate``, may.
"""

import re
from collections.abc import Collection, Mapping, Sequence

from django.core.exceptions import ImproperlyConfigured
from django.http.request import validate_host

OWNER_CREDENTIAL_VARS = ("DATABASE_MIGRATION_URL", "ERP_OWNER_PASSWORD", "POSTGRES_PASSWORD")


def assert_runtime_has_no_owner_credentials(
    environ: Mapping[str, str], *, database_user: str, owner_roles: set[str]
) -> None:
    if environ.get("ERP_PROCESS_ROLE", "") == "migrate":
        return
    leaked = [name for name in OWNER_CREDENTIAL_VARS if environ.get(name)]
    if leaked:
        raise ImproperlyConfigured(
            "Runtime processes must not receive database owner/superuser credentials "
            f"({', '.join(leaked)}). Only the migrate service may (ERP_PROCESS_ROLE=migrate)."
        )
    if database_user in owner_roles:
        raise ImproperlyConfigured(
            "DATABASE_URL uses a privileged database role; runtime processes must use the "
            "runtime role (erp_app)."
        )


# --------------------------------------------------------------------------- host policy (M3)
# Names that must never be a production tenant base domain (Phase 3 plan §10.2, D1).
_PLACEHOLDER_NAMES = frozenset(
    {
        "localhost",
        "test",
        "example",
        "invalid",
        "local",
        "example.com",
        "example.net",
        "example.org",
    }
)
_PLACEHOLDER_SUFFIXES = (
    ".localhost",
    ".test",
    ".example",
    ".invalid",
    ".local",
    ".example.com",
    ".example.net",
    ".example.org",
)
_DOMAIN = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")


def is_placeholder_domain(domain: str) -> bool:
    return domain in _PLACEHOLDER_NAMES or domain.endswith(_PLACEHOLDER_SUFFIXES)


def assert_host_configuration(
    *,
    platform_hosts: Sequence[str],
    allowed_hosts: Sequence[str],
    tenant_hosts_enabled: bool,
    tenant_base_domain: str,
    reserved_labels: Collection[str],
    production: bool,
) -> None:
    """Refuse host settings that would blur platform and tenant hosts.

    Every environment: a platform host may sit under the tenant base domain only with a
    reserved label (``admin.<domain>``), so it can never collide with a tenant slug.
    Production: platform hosts are mandatory and allowed; tenant hosts can be enabled only
    with a real, allowed base domain (never a placeholder or reserved name).
    """
    for host in platform_hosts:
        if host != host.strip().lower() or ":" in host or not host:
            raise ImproperlyConfigured(
                f"PLATFORM_HOSTS entries must be lower-case host names without a port: {host!r}."
            )
        if tenant_base_domain and host.endswith("." + tenant_base_domain):
            label = host[: -len(tenant_base_domain) - 1]
            if "." not in label and label not in reserved_labels:
                raise ImproperlyConfigured(
                    f"Platform host {host!r} could be a tenant host; use a reserved label."
                )
    if not production:
        return
    if not platform_hosts:
        raise ImproperlyConfigured("PLATFORM_HOSTS must be set in production.")
    for host in platform_hosts:
        if not validate_host(host, list(allowed_hosts)):
            raise ImproperlyConfigured(f"Platform host {host!r} is not in DJANGO_ALLOWED_HOSTS.")
    if not tenant_hosts_enabled:
        return
    if not tenant_base_domain or not _DOMAIN.match(tenant_base_domain):
        raise ImproperlyConfigured(
            "TENANT_HOSTS_ENABLED requires TENANT_BASE_DOMAIN to be a real domain name."
        )
    if is_placeholder_domain(tenant_base_domain):
        raise ImproperlyConfigured(
            "TENANT_BASE_DOMAIN is a placeholder or reserved name; tenant hosts stay disabled "
            "until the production domain is provided (D1)."
        )
    if not validate_host(f"tenant-probe.{tenant_base_domain}", list(allowed_hosts)):
        raise ImproperlyConfigured(
            "DJANGO_ALLOWED_HOSTS must cover the tenant hosts (add '.<TENANT_BASE_DOMAIN>')."
        )


def assert_no_persistent_connections(databases: Mapping[str, Mapping[str, object]]) -> None:
    """D4: production runs with ``CONN_MAX_AGE = 0`` on every alias. A persistent setting needs
    owner approval and leak tests, i.e. a reviewed change to this guard."""
    for alias, config in databases.items():
        if config.get("CONN_MAX_AGE", 0) != 0:
            raise ImproperlyConfigured(
                f"DATABASES[{alias!r}] must use CONN_MAX_AGE = 0 in production (D4)."
            )
