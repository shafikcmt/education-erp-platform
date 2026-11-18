"""Leak detectors at request and task boundaries (Phase 3 plan §8.5 L8, C5).

At the start and end of every request and Celery task, no tenant context, no platform
operation and no per-connection tenant transaction state may exist. Anything found is cleared
(defense in depth) and reported: logged as an error (Sentry picks it up) and, when
``TENANCY_LEAK_STRICT`` is on (tests), raised as :class:`TenantContextLeak`.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.db import connections

from apps.core.tenancy.context import _PLATFORM_OPERATION, _reset_for_boundary
from apps.core.tenancy.exceptions import TenantContextLeak
from apps.core.tenancy.transaction import _APPLYING_ATTR, _STATE_ATTR, connections_with_tenant_state

logger = logging.getLogger("apps.core.tenancy")


def check_boundary(where: str) -> None:
    """Clear and report any tenant state that survived to a boundary."""
    leaked = _reset_for_boundary()
    operation = _PLATFORM_OPERATION.get()
    if operation is not None:
        _PLATFORM_OPERATION.set(None)
    aliases = connections_with_tenant_state()
    for conn in connections.all(initialized_only=True):
        if conn.alias in aliases:
            setattr(conn, _STATE_ATTR, None)
            setattr(conn, _APPLYING_ATTR, None)
    if leaked is None and operation is None and not aliases:
        return
    logger.error(
        "tenancy.context_leak",
        extra={
            "boundary": where,
            "leaked_tenant_id": str(leaked.id) if leaked else "",
            "platform_operation": getattr(operation, "operation_id", ""),
            "aliases": aliases,
        },
    )
    if getattr(settings, "TENANCY_LEAK_STRICT", False):
        raise TenantContextLeak(f"Tenant state leaked to the {where} boundary.")


def on_request_started(**_: Any) -> None:
    check_boundary("request_started")


def on_request_finished(**_: Any) -> None:
    check_boundary("request_finished")


def _eager(task: Any) -> bool:
    """An eager task runs inside its caller (tests, or ``apply()``): it is not a boundary.
    ``TenantTask``/``PlatformTask`` isolate it instead (Phase 3 M7, C6)."""
    return bool(getattr(getattr(task, "request", None), "is_eager", False))


def on_task_prerun(task: Any = None, **_: Any) -> None:
    if not _eager(task):
        check_boundary("task_prerun")


def on_task_postrun(task: Any = None, **_: Any) -> None:
    if not _eager(task):
        check_boundary("task_postrun")
