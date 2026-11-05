"""Production settings. Secrets and hosts MUST come from the environment (no defaults)."""

from django.core.exceptions import ImproperlyConfigured

from .base import *
from .base import ALLOWED_HOSTS, SECRET_KEY, env

DEBUG = False

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set in production.")
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith(("dev-", "test-", "change-me")):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be a strong, unique production secret.")

# Transport security (TLS terminates at Nginx).
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_REDIRECT_EXEMPT = [r"^healthz$", r"^readyz$"]  # internal probes over plain HTTP
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31_536_000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False  # opt-in decision for later; preload is hard to undo

# ADR-011 cookie hardening. `__Host-` prefix forces Secure + Path=/ + no Domain.
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_NAME = "__Host-sessionid"

API_DOCS_ENABLED = env.bool("API_DOCS_ENABLED", default=False)
