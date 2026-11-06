"""Production settings. Secrets and hosts MUST come from the environment (no defaults)."""

from django.core.exceptions import ImproperlyConfigured

from .base import *
from .base import ALLOWED_HOSTS, SECRET_KEY, env

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

# The OpenAPI schema/docs must not be public in production (docs/SECURITY.md). It stays off
# regardless of the environment until platform-staff-only access exists (Phase 2/3).
API_DOCS_ENABLED = False
