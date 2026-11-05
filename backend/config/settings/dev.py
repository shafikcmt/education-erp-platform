"""Local development settings (docker compose / developer machine). Never used in production."""

from .base import *
from .base import env

DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "api", ".localhost"]
)
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["http://localhost:8080"])

# Local HTTP: secure-cookie flags are relaxed only here (prod enforces them).
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=False)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=False)

API_DOCS_ENABLED = env.bool("API_DOCS_ENABLED", default=True)
