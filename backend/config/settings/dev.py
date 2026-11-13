"""Local development settings (docker compose / developer machine). Never used in production."""

import os

from apps.core.config_guards import (
    assert_host_configuration,
    assert_runtime_has_no_owner_credentials,
)
from apps.tenancy.rules import RESERVED_SLUGS

from .base import *
from .base import DATABASES, TENANT_HOSTS_ENABLED, env

DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "api", ".localhost"]
)
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["http://localhost:8080"])
# Host policy (Phase 3 plan §10.3). ``api`` is the compose service name the Next.js server
# uses for server-side requests. Tenant hosts ({slug}.localhost) stay off unless enabled.
PLATFORM_HOSTS = [
    h.strip().lower()
    for h in env.list("PLATFORM_HOSTS", default=["localhost", "127.0.0.1", "api"])
    if h.strip()
]
TENANT_BASE_DOMAIN = env.str("TENANT_BASE_DOMAIN", default="localhost").strip().lower()

# Local HTTP: secure-cookie flags are relaxed only here (prod enforces them).
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=False)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=False)

API_DOCS_ENABLED = env.bool("API_DOCS_ENABLED", default=True)

# Behind the dev Nginx, which overwrites X-Real-IP with the client address.
CLIENT_IP_HEADER = env.str("CLIENT_IP_HEADER", default="HTTP_X_REAL_IP")

# Security review H3: runtime processes must not hold owner/superuser DB credentials.
assert_runtime_has_no_owner_credentials(
    os.environ,
    database_user=str(DATABASES["default"].get("USER", "")),
    owner_roles={env.str("DATABASE_OWNER_ROLE", default="erp_owner"), "postgres"},
)

assert_host_configuration(
    platform_hosts=PLATFORM_HOSTS,
    allowed_hosts=ALLOWED_HOSTS,
    tenant_hosts_enabled=TENANT_HOSTS_ENABLED,
    tenant_base_domain=TENANT_BASE_DOMAIN,
    reserved_labels=RESERVED_SLUGS,
    production=False,
)
