"""Run code on a fresh, *unwrapped* database connection (tests only).

pytest-django wraps every alias of a test in a transaction, so real COMMIT / ROLLBACK,
``on_commit`` and connection-reuse behaviour are exercised in a worker thread, which gets its
own connection outside that transaction. Data committed there must be cleaned up by the test.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from django.db import connections


def in_thread[T](fn: Callable[..., T], *args: Any) -> T:
    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["result"] = fn(*args)
        except BaseException as exc:
            box["error"] = exc
        finally:
            connections.close_all()

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    result: T = box["result"]
    return result


def delete_probe_rows(*tenants: Any) -> None:
    """Remove committed probe rows of ``tenants`` (in a worker thread)."""
    from apps.core.tenancy import tenant_atomic
    from tests.isolation_app.models import ProbeRecord

    def run() -> None:
        for tenant in tenants:
            with tenant_atomic(tenant):
                ProbeRecord.objects.all().delete()

    in_thread(run)
