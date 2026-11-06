"""Startup guards for deployment configuration (security review H3).

Runtime processes (API, Celery worker/beat) must never hold database owner or superuser
credentials: the owner role can disable the audit triggers. Only the one-shot migration/ops
process, marked ``ERP_PROCESS_ROLE=migrate``, may.
"""

from collections.abc import Mapping

from django.core.exceptions import ImproperlyConfigured

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
