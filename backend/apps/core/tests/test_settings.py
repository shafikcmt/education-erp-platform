"""Security baseline of the production settings module (evaluated in a clean subprocess)."""

import base64
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings

BACKEND_DIR = Path(__file__).resolve().parents[3]

PROD_ENV = {
    "DJANGO_SETTINGS_MODULE": "config.settings.prod",
    "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),  # fresh random key per test run
    "DJANGO_ALLOWED_HOSTS": "app.example.com",
    "PLATFORM_HOSTS": "app.example.com",
    "DATABASE_URL": "postgres://erp_app:x@db:5432/erp",
    "REDIS_URL": "redis://redis:6379/0",
    "CELERY_BROKER_URL": "redis://redis:6379/1",
    "CELERY_RESULT_BACKEND": "redis://redis:6379/2",
    "S3_BUCKET": "b",
    "S3_ENDPOINT_URL": "https://s3.example.com",
    "S3_ACCESS_KEY_ID": "k",
    "S3_SECRET_ACCESS_KEY": "s",
    # Fresh random keys per run (ADR-031/036); prod refuses missing or dev/test keys.
    "FIELD_ENCRYPTION_KEYS": "prod1:" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    "IP_INDEX_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
}

PROBE = """
import json, django
from django.conf import settings as s
django.setup()
print(json.dumps({k: getattr(s, k) for k in [
  "DEBUG","SECURE_SSL_REDIRECT","SECURE_HSTS_SECONDS","SECURE_HSTS_INCLUDE_SUBDOMAINS",
  "SESSION_COOKIE_SECURE","SESSION_COOKIE_HTTPONLY","SESSION_COOKIE_SAMESITE",
  "SESSION_COOKIE_DOMAIN","SESSION_COOKIE_NAME","SESSION_ENGINE","CSRF_COOKIE_SECURE",
  "CSRF_COOKIE_SAMESITE","CSRF_COOKIE_DOMAIN","CSRF_COOKIE_NAME","CSRF_COOKIE_PATH",
  "SESSION_COOKIE_PATH","X_FRAME_OPTIONS","SECURE_CONTENT_TYPE_NOSNIFF",
  "PASSWORD_HASHERS","API_DOCS_ENABLED","AUTH_USER_MODEL","SECURE_PROXY_SSL_HEADER"]}
  | {"DRF_AUTH": s.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"],
     "DRF_PERMS": s.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"],
     "S3": s.STORAGES["default"]["OPTIONS"]}))
"""


def _run(env_overrides: dict[str, str | None]) -> subprocess.CompletedProcess[str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("DJANGO_", "DATABASE_", "ERP_", "POSTGRES_"))
    }
    env.update(PROD_ENV)
    for key, value in env_overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return subprocess.run(  # noqa: S603 - fixed interpreter + inline probe, no user input
        [sys.executable, "-c", PROBE],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="module")
def prod():
    result = _run({})
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_prod_debug_off_and_transport_security(prod):
    assert prod["DEBUG"] is False
    assert prod["SECURE_SSL_REDIRECT"] is True
    assert prod["SECURE_HSTS_SECONDS"] >= 31_536_000
    assert prod["SECURE_HSTS_INCLUDE_SUBDOMAINS"] is True
    assert prod["SECURE_PROXY_SSL_HEADER"] == ["HTTP_X_FORWARDED_PROTO", "https"]


def test_prod_session_cookie_matches_adr_011(prod):
    assert prod["SESSION_COOKIE_SECURE"] is True
    assert prod["SESSION_COOKIE_HTTPONLY"] is True
    assert prod["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert prod["SESSION_COOKIE_DOMAIN"] is None  # host-only: never shared across tenants
    assert prod["SESSION_COOKIE_NAME"].startswith("__Host-")
    assert prod["SESSION_ENGINE"] == "django.contrib.sessions.backends.cached_db"
    assert prod["CSRF_COOKIE_SECURE"] is True
    assert prod["CSRF_COOKIE_SAMESITE"] == "Lax"
    assert prod["CSRF_COOKIE_DOMAIN"] is None


def test_prod_headers_hashing_and_api_defaults(prod):
    assert prod["X_FRAME_OPTIONS"] == "DENY"
    assert prod["SECURE_CONTENT_TYPE_NOSNIFF"] is True
    assert prod["PASSWORD_HASHERS"][0].endswith("Argon2PasswordHasher")
    assert prod["API_DOCS_ENABLED"] is False
    assert prod["AUTH_USER_MODEL"] == "identity.User"
    assert prod["DRF_AUTH"] == ["apps.identity.authentication.SessionAuthentication"]
    assert prod["DRF_PERMS"] == ["rest_framework.permissions.IsAuthenticated"]


def test_prod_storage_is_private_with_presigned_urls(prod):
    assert prod["S3"]["querystring_auth"] is True
    assert prod["S3"]["default_acl"] is None
    assert prod["S3"]["file_overwrite"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"DJANGO_SECRET_KEY": None},
        {"DJANGO_SECRET_KEY": "dev-insecure-change-me-local-only-0000000000000000000000"},
        {"DJANGO_SECRET_KEY": "short"},
        {"DJANGO_SECRET_KEY": "p" * 64},  # long but low-entropy
        {"DJANGO_SECRET_KEY": "django-insecure-" + "a1b2c3d4e5" * 5},
        {"DJANGO_ALLOWED_HOSTS": None},
        {"FIELD_ENCRYPTION_KEYS": None},
        {"IP_INDEX_KEY": None},
        {"FIELD_ENCRYPTION_KEYS": "dev1:" + base64.urlsafe_b64encode(b"x" * 32).decode()},
        {"FIELD_ENCRYPTION_KEYS": "test1:" + base64.urlsafe_b64encode(b"y" * 32).decode()},
        {"FIELD_ENCRYPTION_KEYS": "prod1:" + base64.urlsafe_b64encode(b"y" * 32).decode()},
        {"IP_INDEX_KEY": base64.urlsafe_b64encode(b"i" * 32).decode()},
        # Phase 3 M3: host policy (D1) and connection handling (D4).
        {"PLATFORM_HOSTS": None},
        {"PLATFORM_HOSTS": "other.example.com"},
        {"TENANT_HOSTS_ENABLED": "true"},
        {"TENANT_HOSTS_ENABLED": "true", "TENANT_BASE_DOMAIN": "localhost"},
        {"TENANT_HOSTS_ENABLED": "true", "TENANT_BASE_DOMAIN": "tenants.example.com"},
        {"DATABASE_CONN_MAX_AGE": "60"},
    ],
)
def test_prod_refuses_to_start_with_unsafe_configuration(overrides):
    result = _run(overrides)
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr


def test_prod_ignores_attempts_to_enable_debug_or_public_api_docs():
    result = _run({"DJANGO_DEBUG": "true", "API_DOCS_ENABLED": "true"})
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout.strip().splitlines()[-1])
    assert values["DEBUG"] is False
    assert values["API_DOCS_ENABLED"] is False


def test_prod_passes_django_deployment_checklist():
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("DJANGO_", "DATABASE_", "ERP_", "POSTGRES_"))
    }
    env.update(PROD_ENV)
    result = subprocess.run(
        [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_base_and_dev_keep_argon2_first():
    from config.settings import base

    assert base.PASSWORD_HASHERS[0].endswith("Argon2PasswordHasher")
    # test settings deliberately use a fast hasher; confirm we are not running prod by mistake
    assert settings.PASSWORD_HASHERS == ["django.contrib.auth.hashers.MD5PasswordHasher"]


def test_prod_csrf_cookie_uses_host_prefix(prod):
    """Review L6: Secure + Path=/ + no Domain, so sibling subdomains can't plant it."""
    assert prod["CSRF_COOKIE_NAME"] == "__Host-csrftoken"
    assert prod["CSRF_COOKIE_SECURE"] is True
    assert prod["CSRF_COOKIE_PATH"] == "/" and prod["CSRF_COOKIE_DOMAIN"] is None
    assert prod["SESSION_COOKIE_PATH"] == "/" and prod["SESSION_COOKIE_DOMAIN"] is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"DATABASE_MIGRATION_URL": "postgres://erp_owner:x@db:5432/erp"},
        {"ERP_OWNER_PASSWORD": "owner-secret"},
        {"POSTGRES_PASSWORD": "superuser-secret"},
        {"DATABASE_URL": "postgres://erp_owner:x@db:5432/erp"},
        {"DATABASE_URL": "postgres://postgres:x@db:5432/erp"},
    ],
)
def test_prod_runtime_refuses_owner_credentials(overrides):
    """Review H3: a runtime process holding owner/superuser credentials refuses to start."""
    result = _run(overrides)
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr


def test_prod_migrate_process_may_hold_owner_credentials():
    result = _run(
        {
            "DATABASE_MIGRATION_URL": "postgres://erp_owner:x@db:5432/erp",
            "DATABASE_URL": "postgres://erp_owner:x@db:5432/erp",
            "ERP_PROCESS_ROLE": "migrate",
        }
    )
    assert result.returncode == 0, result.stderr


def test_tenant_hosts_are_off_and_connections_are_not_persistent_by_default():
    """D1 and D4, for every settings module: this process runs the test settings; base, dev
    and prod defaults are read in clean subprocesses."""
    assert settings.TENANT_HOSTS_ENABLED is False
    assert {a: c["CONN_MAX_AGE"] for a, c in settings.DATABASES.items()} == {
        "default": 0,
        "isolation_secondary": 0,
        "audit_durable": 0,
    }
    probe = (
        "import json, django; from django.conf import settings as s; django.setup(); "
        "print(json.dumps([s.TENANT_HOSTS_ENABLED, s.PLATFORM_HOSTS, s.TENANT_BASE_DOMAIN, "
        "{a: c['CONN_MAX_AGE'] for a, c in s.DATABASES.items()}]))"
    )
    for module, hosts, domain in (
        ("config.settings.prod", ["app.example.com"], ""),
        ("config.settings.dev", ["localhost", "127.0.0.1", "api"], "localhost"),
    ):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "DATABASE_"))}
        env.update(PROD_ENV | {"DJANGO_SETTINGS_MODULE": module})
        if module.endswith("dev"):
            env.pop("PLATFORM_HOSTS")
            env["DJANGO_ALLOWED_HOSTS"] = "localhost,127.0.0.1,api,.localhost"
        for name in ("TENANT_HOSTS_ENABLED", "TENANT_BASE_DOMAIN", "ERP_PROCESS_ROLE"):
            env.pop(name, None)
        result = subprocess.run(  # noqa: S603 - fixed interpreter and inline probe
            [sys.executable, "-c", probe], cwd=BACKEND_DIR, env=env, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
        enabled, platform_hosts, base_domain, ages = json.loads(
            result.stdout.strip().splitlines()[-1]
        )
        assert enabled is False, module
        assert (platform_hosts, base_domain) == (hosts, domain), module
        assert ages == {"default": 0, "audit_durable": 0}, module
