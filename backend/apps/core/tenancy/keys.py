"""Tenant-prefixed cache and storage keys, and the external-I/O guard (Phase 3 plan §8.4.3,
§8.7; CLAUDE.md §10.6-10.7; M7).

* :func:`tenant_cache_key` — ``t:{tenant_id}:...``. Tenant modules never build cache keys by
  hand (static check), so two tenants can't share a cache entry.
* :func:`tenant_storage_key` — ``tenants/{tenant_id}/...`` for object storage; refuses empty
  parts, ``.``/``..``, absolute paths, backslashes and control characters. The ``files`` module
  (uploads, presigned URLs, virus scanning, quotas) arrives in Phase 6/7 (Q11).
* :func:`assert_no_open_tenant_transaction` — email, HTTP and storage calls must not run inside
  an open tenant transaction (they go through ``on_commit`` or a Celery task). The test email
  backend and :func:`tenant_storage` call it.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from django.core.files.storage import Storage, default_storage
from django.db import connections

from apps.core.tenancy.context import TenantContext, require_tenant
from apps.core.tenancy.exceptions import TenantIsolationError
from apps.core.tenancy.transaction import applied_tenant_id

_CACHE_PART = re.compile(r"[A-Za-z0-9_.\-@]+")
_STORAGE_PART = re.compile(r"[A-Za-z0-9_.\-]+")


class ExternalIOInTenantTransaction(TenantIsolationError):  # noqa: N818 - plan naming family
    """Email, HTTP or storage I/O was attempted inside an open tenant transaction."""


def _tenant_id(tenant: TenantContext | uuid.UUID | str | None) -> uuid.UUID:
    """The bound tenant, or an explicitly given one (any well-formed UUID: a key is a
    namespace, not an authorization decision)."""
    if tenant is None:
        return require_tenant().id
    if isinstance(tenant, TenantContext):
        return tenant.id
    if isinstance(tenant, uuid.UUID):
        return tenant
    try:
        return uuid.UUID(str(tenant))
    except ValueError as exc:
        raise ValueError("Tenant id must be a UUID.") from exc


def tenant_cache_key(*parts: Any, tenant: TenantContext | uuid.UUID | str | None = None) -> str:
    """``t:{tenant}:part:part`` for the bound tenant (or ``tenant``)."""
    cleaned = [str(part) for part in parts]
    if not cleaned or not all(_CACHE_PART.fullmatch(part) for part in cleaned):
        raise ValueError("Cache key parts must be non-empty and use [A-Za-z0-9_.-@] only.")
    return ":".join(("t", str(_tenant_id(tenant)), *cleaned))


def tenant_storage_key(*parts: str, tenant: TenantContext | uuid.UUID | str | None = None) -> str:
    """``tenants/{tenant}/part/part`` for the bound tenant (or ``tenant``)."""
    cleaned = [str(part) for part in parts]
    if not cleaned:
        raise ValueError("A storage key needs at least one part.")
    for part in cleaned:
        if part in {".", ".."} or not _STORAGE_PART.fullmatch(part):
            raise ValueError(f"Invalid storage key part: {part!r}")
    return "/".join(("tenants", str(_tenant_id(tenant)), *cleaned))


def assert_no_open_tenant_transaction(what: str) -> None:
    """Refuse external I/O while a tenant transaction is open on any connection (outside a
    Celery task body, which is the intended place for it)."""
    from apps.core.tasking import in_task

    if in_task():
        return
    for conn in connections.all(initialized_only=True):
        if conn.in_atomic_block and applied_tenant_id(conn) is not None:
            raise ExternalIOInTenantTransaction(
                f"{what} inside an open tenant transaction: use on_commit or a Celery task."
            )


def tenant_storage() -> Storage:
    """The object storage, for code that is about to do storage I/O."""
    assert_no_open_tenant_transaction("Storage access")
    return default_storage
