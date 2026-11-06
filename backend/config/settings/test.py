"""Test settings (pytest).

Tests run against real PostgreSQL 17 (never SQLite) — see docs/TESTING_STRATEGY.md.
The test database is created and migrated as the owner role (``DATABASE_MIGRATION_URL``);
``tests/conftest.py`` then switches the connection to the runtime role ``erp_app`` so every
test runs with production-equivalent privileges (NOSUPERUSER, NOBYPASSRLS — ADR-009).
"""

import os

# Sensible local defaults so `pytest` works against the compose Postgres/Redis on localhost.
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-insecure-secret-key-not-for-production")
os.environ.setdefault("DATABASE_URL", "postgres://erp_app:erp_app_dev_password@localhost:5432/erp")
os.environ.setdefault(
    "DATABASE_MIGRATION_URL", "postgres://erp_owner:erp_owner_dev_password@localhost:5432/erp"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/9")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")
os.environ.setdefault("S3_BUCKET", "erp-test")
os.environ.setdefault("S3_ENDPOINT_URL", "http://localhost:8333")
os.environ.setdefault("S3_ACCESS_KEY_ID", "test-access-key")
os.environ.setdefault("S3_SECRET_ACCESS_KEY", "test-secret-key")
# Test-only keys (ADR-031/036). Two keys so rotation paths are exercised.
os.environ.setdefault(
    "FIELD_ENCRYPTION_KEYS",
    "test2:VGVzdEtleTItdGVzdC1vbmx5LW5vdC1hLXNlY3JldCE,"
    "test1:VGVzdEtleTEtdGVzdC1vbmx5LW5vdC1hLXNlY3JldCE",
)
os.environ.setdefault("IP_INDEX_KEY", "dHR0dHR0dHR0dHR0dHR0dHR0dHR0dHR0dHR0dHR0dHQ")  # dummy, low entropy

from apps.core.logging import build_logging_config

from .base import *
from .base import env

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]

# Create/migrate the test database as the owner role; conftest switches to erp_app afterwards.
_app_db = env.db("DATABASE_URL")
DATABASES = {"default": env.db("DATABASE_MIGRATION_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = 0
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DATABASES["default"]["TEST"] = {"NAME": "test_erp"}
TEST_APP_DB_USER: str = _app_db["USER"]
TEST_APP_DB_PASSWORD: str = _app_db["PASSWORD"]

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
SESSION_ENGINE = "django.contrib.sessions.backends.db"

STORAGES["default"] = {"BACKEND": "django.core.files.storage.InMemoryStorage"}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Fast hashing in tests only; prod/dev keep Argon2 first (asserted in tests).
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
LOGGING = build_logging_config(level="WARNING", fmt="console")
SENTRY_DSN = ""
