"""Platform Celery tasks and the task declaration rule (Phase 3 M7; plan §8.5 C1-C10).

Every task is declared as exactly one of:

* a **platform task** (:func:`platform_task`): no tenant context, bound to a catalogued
  platform operation (plan §6.3) that a system actor may run;
* a **tenant task** (``apps.tenancy.tasking.tenant_task``): runs for ONE tenant passed
  explicitly as ``tenant_id``, inside that tenant's transaction.

A CI test fails for any registered task that is neither. Beat schedules only platform tasks;
fan-out platform tasks enqueue one tenant task per tenant (mechanism I).

A platform task never runs with a tenant context: when it is executed eagerly from inside a
tenant request (tests, ``apply()``), the caller's context is unbound for the duration of the
task and restored afterwards.
"""

from __future__ import annotations

import contextvars
from collections.abc import Callable
from typing import Any

from celery import Task, shared_task

from apps.core.tenancy.context import _CURRENT
from apps.core.tenancy.platform import CATALOGUE

PLATFORM = "platform"
TENANT = "tenant"

# True while a Celery task body runs (any kind): external I/O inside a task is the intended
# place for it, so the test email guard (apps.core.testing) allows it there.
_IN_TASK: contextvars.ContextVar[bool] = contextvars.ContextVar("erp_in_task", default=False)


def in_task() -> bool:
    return _IN_TASK.get()


class DeclaredTask(Task):  # type: ignore[type-arg]
    abstract = True
    erp_kind = ""
    erp_operation = ""

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        token = _IN_TASK.set(True)
        try:
            return self.run_declared(*args, **kwargs)
        finally:
            _IN_TASK.reset(token)

    def run_declared(self, *args: Any, **kwargs: Any) -> Any:
        return super().__call__(*args, **kwargs)


class PlatformTask(DeclaredTask):
    abstract = True
    erp_kind = PLATFORM

    def run_declared(self, *args: Any, **kwargs: Any) -> Any:
        token = _CURRENT.set(None)  # an eager run from a tenant request: no tenant here
        try:
            return super().run_declared(*args, **kwargs)
        finally:
            _CURRENT.reset(token)


def platform_task(*, name: str, operation: str, **options: Any) -> Callable[..., Any]:
    """Declare a platform task bound to catalogue operation ``operation``."""
    spec = CATALOGUE.get(operation)
    if spec is None or not spec.enabled or spec.actor != "system":
        raise ValueError(f"{operation!r} is not an enabled system operation of the catalogue.")
    decorator: Callable[..., Any] = shared_task(
        name=name, base=PlatformTask, erp_operation=operation, **options
    )
    return decorator
