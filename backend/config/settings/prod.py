"""Production settings. Secrets and hosts MUST come from the environment (no defaults)."""

import os

from django.core.exceptions import ImproperlyConfigured

from apps.core.config_guards import (
    assert_host_configuration,
    assert_no_persistent_connections,
    assert_runtime_has_no_owner_credentials,
)
from apps.tenancy.rules import RESERVED_SLUGS

from .base import *
from .base import (
    ALLOWED_HOSTS,
    DATABASES,
    FIELD_ENCRYPTION_KEYS,
    IP_INDEX_KEY,
    PLATFORM_HOSTS,
    SECRET_KEY,
    TENANT_BASE_DOMAIN,
    TENANT_HOSTS_ENABLED,
    env,
)

DEBUG = False

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set in production.")
# Mirrors Django's security.W009 criteria (length, entropy) plus our dev/test prefixes.
if (
    len(SECRET_KEY) < 50
    or len(set(SECRET_KEY)) < 5
    or SECRET_KEY.startswith(("dev-", "test-", "change-me", "django-insecure-"))
):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be a strong, unique production secret.")

# Secrets at rest (ADR-031/036): real keys from the secret manager are mandatory. Dummy
# development/test key ids and keys are refused, and the HMAC key must differ from them.
_DUMMY_KEY_ID_PREFIXES = ("dev", "test", "example", "change")
if not FIELD_ENCRYPTION_KEYS or not IP_INDEX_KEY:
    raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS and IP_INDEX_KEY must be set in production.")
for _entry in FIELD_ENCRYPTION_KEYS:
    if _entry.split(":", 1)[0].lower().startswith(_DUMMY_KEY_ID_PREFIXES):
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS contains a development/test key.")
if any(_entry.split(":", 1)[-1] == IP_INDEX_KEY for _entry in FIELD_ENCRYPTION_KEYS):
    raise ImproperlyConfigured("IP_INDEX_KEY must be separate from the encryption keys.")
for _key in (IP_INDEX_KEY, *(_e.split(":", 1)[-1] for _e in FIELD_ENCRYPTION_KEYS)):
    if len(set(_key)) < 16:  # e.g. the low-entropy dummy keys of .env.example / tests
        raise ImproperlyConfigured("Encryption and index keys must be random (low entropy).")

# Behind Nginx, which overwrites X-Real-IP with the client address.
CLIENT_IP_HEADER = env.str("CLIENT_IP_HEADER", default="HTTP_X_REAL_IP")

# Transport security (TLS terminates at Nginx).
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_REDIRECT_EXEMPT = [r"^healthz$", r"^readyz$"]  # internal probes over plain HTTP
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31_536_000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False  # opt-in decision for later; preload is hard to undo
# W021 = "SECURE_HSTS_PRELOAD not set". Deliberate (above), silenced so that
# `check --deploy --fail-level WARNING` is an enforceable CI gate.
SILENCED_SYSTEM_CHECKS = ["security.W021"]

# ADR-011 cookie hardening. `__Host-` prefix forces Secure + Path=/ + no Domain.
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_NAME = "__Host-sessionid"
# Review L6: `__Host-` forces Secure + Path=/ + no Domain, so a sibling (tenant) subdomain can
# never plant or overwrite the CSRF cookie. The frontend reads either name.
CSRF_COOKIE_NAME = "__Host-csrftoken"
SESSION_COOKIE_PATH = "/"
CSRF_COOKIE_PATH = "/"
SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_DOMAIN = None

# The OpenAPI schema/docs must not be public in production (docs/SECURITY.md). It stays off
# regardless of the environment until platform-staff-only access exists (Phase 2/3).
API_DOCS_ENABLED = False

# Security review H3: runtime processes must not hold owner/superuser DB credentials.
assert_runtime_has_no_owner_credentials(
    os.environ,
    database_user=str(DATABASES["default"].get("USER", "")),
    owner_roles={env.str("DATABASE_OWNER_ROLE", default="erp_owner"), "postgres"},
)

# Phase 3 M3 (plan §10.2, D1): platform hosts are mandatory; tenant hosts can be enabled only
# with a real base domain. D4: production never uses persistent database connections.
assert_host_configuration(
    platform_hosts=PLATFORM_HOSTS,
    allowed_hosts=ALLOWED_HOSTS,
    tenant_hosts_enabled=TENANT_HOSTS_ENABLED,
    tenant_base_domain=TENANT_BASE_DOMAIN,
    reserved_labels=RESERVED_SLUGS,
    production=True,
)
assert_no_persistent_connections(DATABASES)
