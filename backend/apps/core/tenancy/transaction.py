"""``tenant_atomic`` and the per-connection query guard (Phase 3 plan §8.1, §8.5; ADR-009 §4,
ADR-042).

Database tenant context is **transaction-local only**:

* ``tenant_atomic`` opens ``transaction.atomic(using)`` and its first statement is
  ``set_config('app.tenant_id', <uuid>, true)``. PostgreSQL discards the value at COMMIT or
  ROLLBACK, and at ROLLBACK TO SAVEPOINT for a savepoint that set it, so a pooled or persistent
  connection never carries a tenant into the next transaction.
* When ``tenant_atomic`` runs inside an enclosing transaction it did not open (for example a
  test transaction or an explicit outer ``atomic``), it creates a savepoint and, on success,
  clears the setting again before releasing it, so the rest of the outer transaction runs
  without a tenant.
* Session-level ``SET`` is never used (static check in ``tests/isolation``).

The query guard is installed on every connection (``connection_created``). Whenever a tenant
context is bound in Python, a query is allowed only if *this connection's* current transaction
has applied *that* tenant. A bound context therefore never makes a query succeed by itself, and
work outside the transaction (``on_commit`` callbacks, new threads, another alias) is refused
with :class:`TenantContextNotApplied` before it reaches PostgreSQL.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.db import connections, transaction
from django.db.backends.base.base import BaseDatabaseWrapper

from apps.core.tenancy.context import (
    _CURRENT,
    TenantContext,
    active_platform_operation,
    require_tenant,
)
from apps.core.tenancy.exceptions import (
    PlatformScopeError,
    TenantContextConflict,
    TenantContextLeak,
    TenantContextNotApplied,
)

_STATE_ATTR = "_erp_tenant_tx"
_APPLYING_ATTR = "_erp_tenant_applying"
_GUARD_MARK = "_erp_tenant_guard"

APPLY_SQL = "SELECT pg_catalog.set_config('app.tenant_id', %s, true)"
CLEAR_SQL = "SELECT pg_catalog.set_config('app.tenant_id', '', true)"
# Transaction-local lock wait limit for request transactions (plan §8.4.2, D9).
LOCK_TIMEOUT_SQL = "SELECT pg_catalog.set_config('lock_timeout', %s, true)"
READ_LOCK_TIMEOUT_SQL = "SELECT pg_catalog.current_setting('lock_timeout')"
_LOCK_TIMEOUT = re.compile(r"^[1-9][0-9]{0,5}(ms|s)$")


@dataclass
class _TxState:
    tenant_id: uuid.UUID
    depth: int
    inside_foreign_atomic: bool


def _state(connection: BaseDatabaseWrapper) -> _TxState | None:
    return getattr(connection, _STATE_ATTR, None)


def applied_tenant_id(connection: BaseDatabaseWrapper) -> uuid.UUID | None:
    """Tenant applied to ``connection``'s *current* transaction (``None`` outside one)."""
    state = _state(connection)
    if state is None or not connection.in_atomic_block:
        return None
    return state.tenant_id


def connections_with_tenant_state() -> list[str]:
    """Aliases whose connection still carries tenant transaction state (boundary checks)."""
    return [
        conn.alias
        for conn in connections.all(initialized_only=True)
        if _state(conn) is not None or getattr(conn, _APPLYING_ATTR, None) is not None
    ]


# --------------------------------------------------------------------------- query guard
def tenant_query_guard(
    execute: Callable[..., Any], sql: str, params: Any, many: bool, context: dict[str, Any]
) -> Any:
    conn: BaseDatabaseWrapper = context["connection"]
    ctx = _CURRENT.get()
    state = _state(conn)
    if ctx is None:
        if state is not None:
            raise TenantContextLeak(
                f"Connection {conn.alias!r} carries tenant state but no tenant context is bound."
            )
        return execute(sql, params, many, context)
    if getattr(conn, _APPLYING_ATTR, None) == ctx.id:
        return execute(sql, params, many, context)  # tenant_atomic's own BEGIN/SAVEPOINT/apply
    if state is None or state.tenant_id != ctx.id or not conn.in_atomic_block:
        raise TenantContextNotApplied(
            f"A tenant context is bound but the current transaction on {conn.alias!r} has not "
            "applied it; use tenant_atomic()."
        )
    return execute(sql, params, many, context)


def install_query_guard(connection: BaseDatabaseWrapper, **_: Any) -> None:
    """Idempotently add the guard to a connection (``connection_created`` receiver)."""
    if not getattr(connection, _GUARD_MARK, False):
        connection.execute_wrappers.append(tenant_query_guard)
        setattr(connection, _GUARD_MARK, True)


def has_query_guard(connection: BaseDatabaseWrapper) -> bool:
    return tenant_query_guard in connection.execute_wrappers


# --------------------------------------------------------------------------- tenant_atomic
@contextmanager
def tenant_atomic(
    tenant: TenantContext | uuid.UUID | str | None = None,
    using: str = "default",
    *,
    lock_timeout: str | None = None,
) -> Iterator[TenantContext]:
    """Run the block in a transaction that has applied ``tenant`` (or the bound tenant).

    * Nested with the **same** tenant on the same connection: a savepoint, setting reused.
    * Nested with a **different** tenant: :class:`TenantContextConflict`.
    * Exceptions roll the transaction (or savepoint) back, which also discards the setting;
      ``on_commit`` callbacks registered inside never run after a rollback.
    * The previous Python context and the connection state are always restored in ``finally``.
    * ``lock_timeout`` (for example ``"5s"``) sets PostgreSQL's lock wait limit for this
      transaction only; it is ignored for a nested block, which keeps the outer limit.
    """
    if lock_timeout is not None and not _LOCK_TIMEOUT.match(lock_timeout):
        raise ValueError("lock_timeout must look like '5s' or '500ms'.")
    if using not in settings.DATABASES:
        raise TenantContextConflict(f"Unknown database alias {using!r}.")
    ctx = TenantContext.coerce(tenant) if tenant is not None else require_tenant()
    bound = _CURRENT.get()
    if bound is not None and bound.id != ctx.id:
        raise TenantContextConflict("Cannot open a transaction for a different tenant.")
    operation = active_platform_operation()
    if operation is not None:
        if not operation.allows_tenant_transactions():
            raise PlatformScopeError(
                f"Platform operation {operation.operation_id} is not catalogued for tenant "
                "transactions."
            )
        operation.touch(ctx.id)

    conn = connections[using]
    install_query_guard(conn)
    state = _state(conn)

    if state is not None and conn.in_atomic_block:
        # Nested inside an outer tenant_atomic on this connection.
        if state.tenant_id != ctx.id:
            raise TenantContextConflict("This transaction already applied a different tenant.")
        state.depth += 1
        token = _CURRENT.set(ctx)
        try:
            with transaction.atomic(using=using):
                yield ctx
        finally:
            state.depth -= 1
            _CURRENT.reset(token)
        return

    if state is not None:
        # State from a transaction that has already ended: never reuse it.
        setattr(conn, _STATE_ATTR, None)
        raise TenantContextLeak(f"Stale tenant state found on connection {using!r}.")

    inside_foreign = conn.in_atomic_block
    token = _CURRENT.set(ctx)
    setattr(conn, _APPLYING_ATTR, ctx.id)
    try:
        with transaction.atomic(using=using):
            previous_lock_timeout: str | None = None
            with conn.cursor() as cursor:
                cursor.execute(APPLY_SQL, [str(ctx.id)])
                if lock_timeout is not None:
                    if inside_foreign:
                        cursor.execute(READ_LOCK_TIMEOUT_SQL)
                        previous_lock_timeout = cursor.fetchone()[0]
                    cursor.execute(LOCK_TIMEOUT_SQL, [lock_timeout])
            setattr(conn, _STATE_ATTR, _TxState(ctx.id, 1, inside_foreign))
            setattr(conn, _APPLYING_ATTR, None)
            yield ctx
            if not inside_foreign:
                # This block is the outermost transaction and is about to commit. Django runs
                # ``on_commit`` callbacks right after COMMIT, still inside this ``with``: they
                # must find no applied tenant transaction on the connection (Phase 3 M7). A
                # tenant query in a callback is then refused by the guard (L4), and a task run
                # from a callback (eager mode, C6) opens a transaction of its own.
                setattr(conn, _STATE_ATTR, None)
            if inside_foreign and not conn.needs_rollback:
                # The enclosing transaction continues after us: clear the settings before the
                # savepoint is released. (On error, or when the block was marked for rollback
                # with ``set_rollback(True)``, the savepoint rollback reverts them.)
                with conn.cursor() as cursor:
                    cursor.execute(CLEAR_SQL)
                    if previous_lock_timeout is not None:
                        cursor.execute(LOCK_TIMEOUT_SQL, [previous_lock_timeout])
    finally:
        setattr(conn, _STATE_ATTR, None)
        setattr(conn, _APPLYING_ATTR, None)
        _CURRENT.reset(token)
