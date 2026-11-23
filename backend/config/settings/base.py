"""Shared settings for every environment.

All configuration comes from environment variables (12-factor, django-environ).
Environment modules (``dev``, ``test``, ``prod``) import this module and override defaults.
Never put secrets in this file; ``.env.example`` documents every variable with dummy values.
"""

from pathlib import Path
from typing import Any

import environ

from apps.core.logging import build_logging_config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

# --------------------------------------------------------------------------- core
SECRET_KEY: str = env.str("DJANGO_SECRET_KEY")
DEBUG: bool = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS", default=[])
APP_VERSION: str = env.str("APP_VERSION", default="0.1.0")
APP_ENVIRONMENT: str = env.str("APP_ENVIRONMENT", default="local")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "drf_spectacular",
    "storages",
    # project apps (module codes, CLAUDE.md §5)
    "apps.core",
    "apps.identity",
    "apps.rbac",
    "apps.audit",
    "apps.tenancy",
    "apps.module_registry",
    "apps.billing",
    "apps.customization",
    "apps.notifications_core",
    "apps.academics",
    "apps.files",
]

MIDDLEWARE = [
    "apps.core.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # Pure host policy (no I/O) BEFORE sessions: rejected hosts touch no store and no database.
    "apps.tenancy.middleware.HostPolicyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Phase 2: idle/absolute timeouts + SessionRecord upkeep (plan §6.7).
    "apps.identity.middleware.SessionSecurityMiddleware",
    # Phase 3 M3 (plan §8.2, §10.1): F1 resolution, session-host binding and the authorization
    # scope; then one tenant transaction per tenant-host request (platform hosts: autocommit).
    "apps.tenancy.middleware.TenantResolutionMiddleware",
    "apps.tenancy.middleware.TenantTransactionMiddleware",
    "apps.core.middleware.ApiNoStoreMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]

# --------------------------------------------------------------------------- database
# DATABASE_URL is the *runtime* role (erp_app: NOSUPERUSER, NOBYPASSRLS — ADR-009).
# Migrations use DATABASE_MIGRATION_URL (erp_owner); see infra/docker/postgres/init.
DATABASES: dict[str, dict[str, Any]] = {"default": env.db("DATABASE_URL")}
# D4 (Phase 3): no persistent connections. Tenant context is transaction-local, so reuse would
# be safe, but any non-zero value needs owner approval and leak tests; production refuses it
# (core.config_guards). The override exists for non-production measurements only.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=0)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
# Tenant data must run inside explicit tenant transactions (Phase 3, core.db.tenant_atomic);
# ATOMIC_REQUESTS stays off so that wrapper is the single, explicit entry point.
DATABASES["default"]["ATOMIC_REQUESTS"] = False
# Durable security audit (Phase 3 plan §8.3; ADR-042): a second connection with the SAME
# runtime credentials, so denial evidence survives the rollback of the request transaction.
AUDIT_DURABLE_ALIAS = "audit_durable"
DATABASES[AUDIT_DURABLE_ALIAS] = {**DATABASES["default"]}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"  # only for third-party apps; ours use UUIDv7

# --------------------------------------------------------------------------- cache & sessions
REDIS_URL: str = env.str("REDIS_URL")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "erp",
        "TIMEOUT": 300,
    }
}

# ADR-011: Django session authentication for the first-party browser app.
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
SESSION_COOKIE_NAME = env.str("SESSION_COOKIE_NAME", default="sessionid")
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=True)
SESSION_COOKIE_DOMAIN = None  # host-only: never shared across tenant hosts
SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE", default=60 * 60 * 12)
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

CSRF_COOKIE_NAME = "csrftoken"
CSRF_COOKIE_HTTPONLY = False  # frontend reads it to send X-CSRFToken (it is not a credential)
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=True)
CSRF_COOKIE_DOMAIN = None
CSRF_TRUSTED_ORIGINS: list[str] = env.list("CSRF_TRUSTED_ORIGINS", default=[])
CSRF_HEADER_NAME = "HTTP_X_CSRFTOKEN"

# --------------------------------------------------------------------------- auth
AUTH_USER_MODEL = "identity.User"
# Django's ModelBackend, hardened for unactivated accounts and equal timing (plan §6.1).
AUTHENTICATION_BACKENDS = ["apps.identity.backends.EmailBackend"]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {
        "NAME": "apps.identity.validators.MaximumLengthValidator",
        "OPTIONS": {"max_length": 128},
    },
    # ADR-037 (Q4): optional HIBP k-anonymity check; a no-op unless enabled below.
    {"NAME": "apps.identity.validators.BreachedPasswordValidator"},
]
PASSWORD_BREACH_CHECK_ENABLED: bool = env.bool("PASSWORD_BREACH_CHECK_ENABLED", default=False)
PASSWORD_BREACH_CHECK_FAIL_CLOSED: bool = env.bool(
    "PASSWORD_BREACH_CHECK_FAIL_CLOSED", default=False
)
# Outbound host to allow-list when the check is enabled: api.pwnedpasswords.com
PASSWORD_BREACH_CHECK_URL: str = "https://api.pwnedpasswords.com/range/"  # noqa: S105 - URL

# --------------------------------------------------------------------------- secrets at rest
# ADR-031 key ring ("key_id:urlsafe-base64-32-bytes", first key encrypts) and the separate
# ADR-036 HMAC key for IP blind indexes / throttle keys. Never committed; prod refuses dummies.
FIELD_ENCRYPTION_KEYS: list[str] = env.list("FIELD_ENCRYPTION_KEYS", default=[])
IP_INDEX_KEY: str = env.str("IP_INDEX_KEY", default="")
DATABASE_APP_ROLE: str = env.str("DATABASE_APP_ROLE", default="erp_app")
# I1: reversing the audit-protection migrations is refused unless explicitly allowed, and is
# never allowed in production or staging.
ERP_ALLOW_AUDIT_ROLLBACK: bool = env.bool("ERP_ALLOW_AUDIT_ROLLBACK", default=False)

# ------------------------------------------------------------------- Phase 2 security policy
# Header the reverse proxy overwrites with the client address (Nginx: X-Real-IP).
CLIENT_IP_HEADER: str = env.str("CLIENT_IP_HEADER", default="")
FRONTEND_BASE_URL: str = env.str("FRONTEND_BASE_URL", default="http://localhost:8080")
SESSION_IDLE_TIMEOUT_SECONDS: int = env.int("SESSION_IDLE_TIMEOUT_SECONDS", default=30 * 60)
SESSION_ABSOLUTE_TIMEOUT_SECONDS: int = env.int(
    "SESSION_ABSOLUTE_TIMEOUT_SECONDS", default=12 * 60 * 60
)
STEP_UP_TTL_SECONDS = 10 * 60
MFA_PENDING_TTL_SECONDS = 5 * 60
MFA_ENROLLMENT_TTL_SECONDS = 10 * 60
MFA_ISSUER: str = env.str("MFA_ISSUER", default="Education ERP")
# Brute-force limits (plan §6.2): (max events, window seconds).
# The per-IP login limit is tunable: many users behind one NAT address (e.g. a school lab).
SECURITY_THROTTLES: dict[str, tuple[int, int]] = {
    "login_ip": (env.int("SECURITY_LOGIN_IP_LIMIT", default=20), 5 * 60),
    "login_email_failures": (5, 15 * 60),  # global per email: progressive delay only
    "login_email_net_failures": (5, 15 * 60),  # per (email, network): temporary lock
    "mfa_user_failures": (10, 15 * 60),  # per account, across sessions (H1)
    "mfa_attempts": (5, MFA_PENDING_TTL_SECONDS),
    "email_flow_email": (3, 60 * 60),
    "email_flow_ip": (10, 60 * 60),
    "step_up": (5, 15 * 60),
    # Phase 3 M4: invitations, per tenant and per (tenant, email).
    "invite_tenant": (env.int("SECURITY_INVITE_TENANT_LIMIT", default=100), 60 * 60),
    "invite_email": (5, 60 * 60),
    # Phase 3 M8: password attempts when redeeming an invitation for an existing account.
    "invite_accept": (5, 15 * 60),
    # Phase 5 M8: self-service sign-up (per IP: 429; per email: silent).
    "signup_ip": (env.int("SECURITY_SIGNUP_IP_LIMIT", default=5), 60 * 60),
    "signup_email": (3, 24 * 60 * 60),
    "signup_verify_ip": (20, 60 * 60),
}
SECURITY_LOGIN_LOCK_SECONDS = 15 * 60
SECURITY_LOGIN_MAX_DELAY_SECONDS = 30
SECURITY_MFA_LOCK_SECONDS = 15 * 60
SECURITY_NOTICE_INTERVAL_SECONDS = 24 * 60 * 60  # at most one lock notice per user per day
SECURITY_IP_RETENTION_DAYS: int = env.int("SECURITY_IP_RETENTION_DAYS", default=365)
# platform_staff | privileged | all | off  (ADR-037, plan §6.11)
SECURITY_NOTIFY_NEW_SIGNIN: str = env.str("SECURITY_NOTIFY_NEW_SIGNIN", default="platform_staff")
SECURITY_SEEN_DEVICE_DAYS = 90
# Pluggable authorization sources (plan §4.4); Phase 3 appends the tenant sources.
RBAC_PERMISSION_SOURCES: list[str] = [
    "apps.rbac.sources.SelfServiceSource",
    "apps.rbac.sources.PlatformRoleSource",
    # Phase 3 M4: role assignments of the tenant applied to the current transaction.
    "apps.tenancy.rbac_sources.TenantMembershipSource",
    # Phase 3 M5: read-only grants of an approved support session (ADR-045).
    "apps.tenancy.rbac_sources.SupportSessionSource",
]
RBAC_CACHE_TTL_SECONDS = 300

# ------------------------------------------------------------------- Phase 3 tenancy (M1)
# platform_scope hooks (ADR-043): core never imports rbac/audit, so they are configured here.
TENANCY_PLATFORM_AUTHORIZER = "apps.rbac.platform_operations.authorize_platform_operation"
TENANCY_PLATFORM_AUDITOR = "apps.audit.platform_operations.record_platform_operation"
# Raise (instead of only logging) when tenant state leaks to a request/task boundary.
TENANCY_LEAK_STRICT: bool = env.bool("TENANCY_LEAK_STRICT", default=False)
# Host policy (plan §10; ADR-041). Tenant hosts are OFF everywhere by default (D1): only
# PLATFORM_HOSTS are served and every other host gets the uniform 404 with no lookup.
PLATFORM_HOSTS: list[str] = [
    h.strip().lower() for h in env.list("PLATFORM_HOSTS", default=[]) if h.strip()
]
TENANT_BASE_DOMAIN: str = env.str("TENANT_BASE_DOMAIN", default="").strip().lower()
TENANT_HOSTS_ENABLED: bool = env.bool("TENANT_HOSTS_ENABLED", default=False)
# Request-wide tenant transactions (plan §8.4, D9): lock wait limit and slow-request warning.
TENANT_REQUEST_LOCK_TIMEOUT = "5s"
TENANT_TX_WARN_MS = 2000
# Sign-in guards (callables ``(request, user) -> reason | None``): a non-None reason turns a
# correct password into the generic invalid-credentials error (D7).
IDENTITY_SIGN_IN_GUARDS: list[str] = ["apps.tenancy.access.sign_in_guard"]
# Phase 4 M3 (ADR-052, ADR-054): plan limits for tenancy, and provisioning hooks (trial plan).
TENANCY_PLAN_LIMITS = "apps.billing.selectors.plan_limits"
TENANCY_PROVISIONING_HOOKS: list[str] = ["apps.billing.provisioning.start_trial_plan"]
# Phase 5 M2 (ADR-058): new institutions pin their type's default preset; its settings form the
# preset layer of the effective configuration.
TENANCY_INSTITUTION_PRESET = "apps.customization.presets.default_preset_for"
CUSTOMIZATION_PRESET_LAYER = "apps.customization.presets.layer"
# Phase 5 M6: custom field values on tenancy entities (validation, edit checks, masking) and
# the platform defaults of the per-plan Studio quotas (ADR-060 Q5; plans may set these keys).
TENANCY_CUSTOM_FIELDS = "apps.customization.fields"
# Phase 6 M1 (ADR-063): checks run after a configuration version becomes active; a refusal
# undoes the publish (customization never imports the modules that register here).
CUSTOMIZATION_PUBLISH_CHECKS = ["apps.academics.hooks.check_structure_levels"]
STUDIO_QUOTA_DEFAULTS: dict[str, int] = {
    "max_custom_fields_per_entity": 50,
    "max_forms": 20,
    "max_workflows": 20,
    "max_rules": 50,
    "max_templates": 50,
    # Phase 6 M3 (ADR-064): object storage per tenant, in MB (plan key ``max_storage_mb``).
    "max_storage_mb": 1024,
}
# Default institution/campus limits copied onto each new tenant (Q12); overridable per tenant
# by a Super Admin (ADR-010) and replaced by subscription plans in Phase 4.
TENANT_DEFAULT_LIMITS: dict[str, int] = {"max_institutions": 1, "max_campuses": 3}
# Phase 3 M8 (plan §12.2, §10.2): when true, provisioning is refused (409
# ``tenant_hosts_disabled``) while tenant hosts are off. Production sets it; nowhere else does.
TENANT_PROVISIONING_REQUIRES_HOSTS = False
# Phase 5 M8 (ADR-060 Q3, P23): self-service sign-up. OFF unless the deployment turns it on;
# every request still needs a platform administrator's approval before a tenant exists.
TENANCY_SIGNUP_ENABLED: bool = env.bool("TENANCY_SIGNUP_ENABLED", default=False)
TENANCY_SIGNUP_TTL_HOURS = 48  # the verification link
TENANCY_SIGNUP_RETENTION_DAYS = 30  # closed requests are deleted after this
# Reversing tenant-isolation migrations (RLS, tenant context function) is refused unless
# explicitly allowed, and is never allowed in production or staging (plan §19.2).
ERP_ALLOW_ISOLATION_ROLLBACK: bool = env.bool("ERP_ALLOW_ISOLATION_ROLLBACK", default=False)

# --------------------------------------------------------------------------- security headers
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
# TLS terminates at Nginx; trust its forwarded proto header only.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# --------------------------------------------------------------------------- i18n / time
LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("bn", "বাংলা")]  # ADR-021: en + bn; RTL-ready for ar
TIME_ZONE = "UTC"  # store UTC; render in tenant/campus timezone
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------- static & storage
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

S3_BUCKET: str = env.str("S3_BUCKET")
# One source for the S3 connection: the storage backend and the files module's presigning
# (Phase 6 M3) both read it, even when tests swap the storage backend.
S3_CONNECTION: dict[str, str] = {
    "bucket_name": S3_BUCKET,
    "endpoint_url": env.str("S3_ENDPOINT_URL"),
    "access_key": env.str("S3_ACCESS_KEY_ID"),
    "secret_key": env.str("S3_SECRET_ACCESS_KEY"),
    "region_name": env.str("S3_REGION", default="us-east-1"),
}
STORAGES: dict[str, dict[str, Any]] = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            **S3_CONNECTION,
            "addressing_style": "path",
            "signature_version": "s3v4",
            "default_acl": None,
            "querystring_auth": True,  # private objects; presigned URLs only
            "querystring_expire": 300,
            "file_overwrite": False,
        },
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
# Phase 6 M3 (ADR-064): presigned URLs are signed for the endpoint browsers reach (defaults to
# the internal one); a scanner callable decides scan states (default: no scanner, "unscanned").
S3_PUBLIC_ENDPOINT_URL: str = env.str("S3_PUBLIC_ENDPOINT_URL", default="")
FILES_SCANNER = "apps.files.scanning.no_scanner"

# --------------------------------------------------------------------------- DRF / OpenAPI
REST_FRAMEWORK: dict[str, Any] = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.identity.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],  # default deny
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.problem_details_exception_handler",
    "DEFAULT_VERSIONING_CLASS": None,
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
}

SPECTACULAR_SETTINGS: dict[str, Any] = {
    "TITLE": "Education ERP API",
    "DESCRIPTION": "Multi-tenant Education ERP SaaS — REST API v1 (ADR-015).",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]+",
    # Phase 3 M8: several tenancy models have a "status"; name each enum explicitly.
    "ENUM_NAME_OVERRIDES": {
        "TenantStatusEnum": "apps.tenancy.rules.TenantStatus.CHOICES",
        "MembershipStatusEnum": "apps.tenancy.models.Membership.Status",
        "SupportSessionStatusEnum": "apps.tenancy.models.SupportSession.Status",
        "MemberStatusChangeEnum": [("active", "Active"), ("suspended", "Suspended")],
        "AcademicTermKindEnum": "apps.academics.models.Term.Kind",
    },
}
API_DOCS_ENABLED: bool = env.bool("API_DOCS_ENABLED", default=False)

# --------------------------------------------------------------------------- Celery
CELERY_BROKER_URL: str = env.str("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND: str = env.str("CELERY_RESULT_BACKEND")
CELERY_RESULT_EXPIRES = 3600
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]  # never pickle
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 15 * 60
CELERY_TASK_SOFT_TIME_LIMIT = 14 * 60
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_QUEUES_ALL = ("default", "notifications", "reports", "imports", "finance", "ai")
CELERY_TASK_ROUTES = {"identity.deliver_security_email": {"queue": "notifications"}}
CELERY_BEAT_SCHEDULE = {
    "core-heartbeat": {"task": "core.ping", "schedule": 300.0, "options": {"queue": "default"}},
    # ADR-036 retention: anonymise security-event IPs older than SECURITY_IP_RETENTION_DAYS.
    "audit-anonymize-ips": {
        "task": "audit.anonymize_expired_ips",
        "schedule": 24 * 3600.0,
        "options": {"queue": "default"},
    },
    "identity-housekeeping": {
        "task": "identity.housekeeping",
        "schedule": 24 * 3600.0,
        "options": {"queue": "default"},
    },
    # Phase 3 M7: end support sessions whose window has passed (fan-out per tenant).
    "tenancy-support-session-expiry": {
        "task": "tenancy.sweep_support_sessions",
        "schedule": 300.0,
        "options": {"queue": "default"},
    },
    # Phase 3 M10 (plan §14, P14): daily summary of blocked isolation violations.
    # Phase 4 M3 (P19): end lapsed trials, add-ons and overrides; recompute entitlements.
    # Phase 4 M7 (P19): daily usage metering (institutions and campuses).
    "billing-record-usage": {
        "task": "billing.record_usage",
        "schedule": 24 * 60 * 60.0,
        "options": {"queue": "default"},
    },
    # Phase 5 M4 (P24): flag overdue workflow requests and notify who can act.
    "customization-workflow-sla-sweep": {
        "task": "customization.sweep_workflow_sla",
        "schedule": 15 * 60.0,
        "options": {"queue": "default"},
    },
    "module-registry-entitlement-sweep": {
        "task": "module_registry.sweep_entitlements",
        "schedule": 60 * 60.0,
        "options": {"queue": "default"},
    },
    # Phase 5 M8 (P25): expire unverified sign-ups, delete closed ones after the retention.
    "tenancy-purge-signups": {
        "task": "tenancy.purge_signups",
        "schedule": 24 * 60 * 60.0,
        "options": {"queue": "default"},
    },
    # Phase 6 M3 (P27): remove unconfirmed uploads and deleted files' objects.
    "files-housekeeping": {
        "task": "files.housekeeping",
        "schedule": 6 * 60 * 60.0,
        "options": {"queue": "default"},
    },
    "tenancy-isolation-daily-report": {
        "task": "tenancy.report_isolation_denials",
        "schedule": 24 * 60 * 60.0,
        "options": {"queue": "default"},
    },
}

# --------------------------------------------------------------------------- email
EMAIL_BACKEND = env.str("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env.str("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=25)
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", default="no-reply@example.invalid")

# --------------------------------------------------------------------------- logging
LOG_LEVEL: str = env.str("LOG_LEVEL", default="INFO")
LOG_FORMAT: str = env.str("LOG_FORMAT", default="json")  # json | console
LOGGING = build_logging_config(level=LOG_LEVEL, fmt=LOG_FORMAT)

# --------------------------------------------------------------------------- Sentry
SENTRY_DSN: str = env.str("SENTRY_DSN", default="")
SENTRY_TRACES_SAMPLE_RATE: float = env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0)

if SENTRY_DSN:  # pragma: no cover - exercised only with a real DSN
    from apps.core.observability import init_sentry

    init_sentry(
        dsn=SENTRY_DSN,
        environment=APP_ENVIRONMENT,
        release=APP_VERSION,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
    )
