"""Celery task isolation (Phase 3 M7; plan §8.5 C1-C10, §15.3 K6).

Eager tests run the task body in-process; the K6 test runs a real (in-process, threaded)
Celery worker consuming from the broker, with its own database connections and real commits.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from celery import current_app
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db import connection, transaction

from apps.core.ids import new_id
from apps.core.tasking import PLATFORM, TENANT, DeclaredTask
from apps.core.tenancy import (
    TenantContextConflict,
    TenantContextMissing,
    current_tenant,
    tenant_atomic,
)
from apps.core.tenancy.platform import CATALOGUE
from apps.core.tenancy.transaction import connections_with_tenant_state
from apps.tenancy.rules import TenantStatus
from apps.tenancy.tasking import TenantTaskRefused, tenant_task
from tests.isolation.threads import in_thread
from tests.isolation_app import tasks as probe
from tests.isolation_app.models import ProbeRecord

pytestmark = pytest.mark.django_db


def _clean() -> bool:
    return current_tenant() is None and connections_with_tenant_state() == []


# --------------------------------------------------------------------------- C10 declarations
def test_every_task_is_declared_and_beat_schedules_only_platform_tasks():
    current_app.loader.import_default_modules()  # every app's tasks module, as a worker does
    tasks = {
        name: task for name, task in current_app.tasks.items() if not name.startswith("celery.")
    }
    assert {"core.ping", "identity.deliver_security_email", "identity.housekeeping"} <= set(tasks)
    for name, task in tasks.items():
        assert isinstance(task, DeclaredTask), f"{name} is neither a platform nor a tenant task"
        if task.erp_kind == PLATFORM:
            spec = CATALOGUE[task.erp_operation]
            assert spec.enabled and spec.actor == "system", name
        else:
            assert task.erp_kind == TENANT, name
    for entry, config in settings.CELERY_BEAT_SCHEDULE.items():
        task = current_app.tasks[config["task"]]
        assert getattr(task, "erp_kind", "") == PLATFORM, entry


def test_platform_task_needs_an_enabled_system_operation():
    from apps.core.tasking import platform_task

    for operation in ("P99", "P11", "P4"):  # unknown, disabled, user-driven
        with pytest.raises(ValueError, match="system operation"):
            platform_task(name=f"probe.bad_{operation}", operation=operation)


# --------------------------------------------------------------------------- tenant tasks
def test_a_tenant_task_runs_only_in_its_tenant_and_resets(tenant_factory):
    a, b = tenant_factory(), tenant_factory()
    with tenant_atomic(b):
        ProbeRecord.objects.create(name="b-row")
    result = probe.tenant_write_and_read.delay(tenant_id=str(a.id), name="a-row").get()
    assert result["names"] == ["a-row"] and result["raw"] == [str(a.id)]
    assert result["setting"] == result["context"] == str(a.id)
    assert _clean()


@pytest.mark.parametrize(
    "kwargs", [{}, {"tenant_id": "not-a-uuid"}, {"tenant_id": str(uuid.uuid4())}]
)
def test_c7_missing_malformed_and_wrong_version_ids_are_refused(kwargs):
    with pytest.raises(TenantTaskRefused):
        probe.tenant_write_and_read.delay(**kwargs).get()
    assert _clean()


def test_c7_unknown_and_unaccepted_tenants_are_refused(tenant_factory):
    with pytest.raises(TenantTaskRefused, match="unknown"):
        probe.tenant_write_and_read.delay(tenant_id=str(new_id())).get()
    for status in (TenantStatus.SUSPENDED, TenantStatus.PROVISIONING):
        ctx = tenant_factory(status=status)
        with pytest.raises(TenantTaskRefused, match=status):
            probe.tenant_write_and_read.delay(tenant_id=str(ctx.id), name="x").get()
        with tenant_atomic(ctx):
            assert not ProbeRecord.objects.exists()
    suspended = tenant_factory(status=TenantStatus.SUSPENDED)
    assert probe.tenant_suspended_ok.delay(tenant_id=str(suspended.id)).get() == "ran"
    assert _clean()


@pytest.mark.parametrize("soft", [False, True])
def test_c2_c4_a_failing_task_rolls_back_and_leaves_nothing(tenant_factory, soft):
    a = tenant_factory()
    with pytest.raises(SoftTimeLimitExceeded if soft else RuntimeError):
        probe.tenant_fail.delay(tenant_id=str(a.id), soft=soft).get()
    assert _clean()
    with tenant_atomic(a):
        assert not ProbeRecord.objects.exists()
    assert probe.tenant_write_and_read.delay(tenant_id=str(a.id)).get()["context"] == str(a.id)


def test_c3_each_attempt_is_a_fresh_tenant_transaction(tenant_factory):
    """C3: a retry is a new ``__call__``. Each attempt (retries 0, 1, 2) re-establishes the same
    tenant from its own ``tenant_id``, a failed attempt leaves nothing behind, and nothing
    carries over between attempts. (Eager Celery nests ``retry()`` inside the first attempt,
    so attempts are applied one by one, as a worker would deliver them.)"""
    a = tenant_factory()
    calls: list[tuple[int, str | None, str]] = []

    @tenant_task(name=f"probe.attempt_{uuid.uuid4().hex[:6]}", bind=True)
    def attempt(self: Any, *, tenant_id: uuid.UUID) -> int:
        ctx = current_tenant()
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('app.tenant_id', true)")
            setting = str(cursor.fetchone()[0])
        calls.append((self.request.retries, str(ctx.id) if ctx else None, setting))
        ProbeRecord.objects.create(name=f"attempt-{self.request.retries}")
        retries = int(self.request.retries)
        if retries < 2:
            raise RuntimeError("transient failure")
        return retries

    for retries in (0, 1):
        with pytest.raises(RuntimeError, match="transient"):  # eager mode propagates
            attempt.apply(kwargs={"tenant_id": str(a.id)}, retries=retries)
        assert _clean()
    assert attempt.apply(kwargs={"tenant_id": str(a.id)}, retries=2).get() == 2
    assert _clean()
    assert calls == [(n, str(a.id), str(a.id)) for n in (0, 1, 2)]
    with tenant_atomic(a):
        assert list(ProbeRecord.objects.values_list("name", flat=True)) == ["attempt-2"]


def test_c6_eager_from_a_commit_hook_same_tenant_ok_other_tenant_conflict(committed_tenant_pair):
    a, b = committed_tenant_pair

    def run() -> tuple[Any, Any]:
        results: dict[str, Any] = {}

        def same() -> None:
            results["same"] = probe.tenant_write_and_read.apply(
                kwargs={"tenant_id": str(a.id), "name": "from-hook"}
            ).get()

        def other() -> None:
            try:
                probe.tenant_write_and_read.apply(kwargs={"tenant_id": str(b.id)}).get()
            except TenantContextConflict as exc:
                results["other"] = exc

        with tenant_atomic(a):
            transaction.on_commit(same)
            transaction.on_commit(other)
        return results["same"], results.get("other")

    same, other = in_thread(run)
    assert same["names"] == ["from-hook"] and same["context"] == str(a.id)
    assert isinstance(other, TenantContextConflict)


def test_c9_nothing_is_inherited_from_the_caller(tenant_factory):
    a, b = tenant_factory(), tenant_factory()
    with tenant_atomic(a):
        with pytest.raises(TenantContextConflict):
            probe.tenant_write_and_read.delay(tenant_id=str(b.id)).get()
        with pytest.raises(TenantTaskRefused):
            probe.tenant_write_and_read.delay().get()  # no implicit tenant


# --------------------------------------------------------------------------- platform tasks
def test_platform_tasks_never_see_a_tenant(tenant_factory):
    a = tenant_factory()
    with tenant_atomic(a):
        ProbeRecord.objects.create(name="a-row")
    assert probe.platform_sees.delay().get() == {"setting": "", "raw": [], "context": None}
    with pytest.raises(TenantContextMissing):  # C8
        probe.platform_tenant_query.delay().get()
    assert _clean()


# --------------------------------------------------------------------------- K6 real worker
def test_k6_a_real_worker_interleaves_tenants_without_leaks(committed_tenant_pair, settings):
    """K6 (and C1): a real Celery worker (in-process, 2 threads, memory broker) runs
    interleaved tasks for A and B with real commits; every task sees only its tenant and the
    leak detectors at task_prerun/postrun stay silent. The prefork variant through the compose
    worker belongs to the M10 stack tests."""
    import logging

    from celery.contrib.testing.worker import start_worker

    a, b = committed_tenant_pair
    leaks: list[logging.LogRecord] = []

    class Catch(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.getMessage() == "tenancy.context_leak":
                leaks.append(record)

    handler = Catch()
    logging.getLogger("apps.core.tenancy").addHandler(handler)
    current_app.conf.task_always_eager = False
    try:
        with start_worker(current_app, pool="threads", concurrency=2, perform_ping_check=False):
            results = [
                probe.tenant_write_and_read.delay(tenant_id=str(t.id), name=f"k6-{t.id}-{i}")
                for i in range(20)
                for t in (a, b)
            ]
            seen = [r.get(timeout=60) for r in results]
    finally:
        current_app.conf.task_always_eager = True
        logging.getLogger("apps.core.tenancy").removeHandler(handler)
    for result in seen:
        tenant_id = result["tenant_id"]
        assert result["setting"] == result["context"] == tenant_id
        assert result["raw"] == [tenant_id]
        assert all(name.startswith(f"k6-{tenant_id}-") for name in result["names"])
    assert leaks == []
    counts = in_thread(lambda: {t.id: _count(t) for t in (a, b)})
    assert counts == {a.id: 20, b.id: 20}


def _count(tenant: Any) -> int:
    with tenant_atomic(tenant):
        return ProbeRecord.objects.count()


# --------------------------------------------------------------------------- support expiry
def test_support_session_sweep_expires_lapsed_sessions_per_tenant(org, tenant_site):
    from datetime import timedelta

    from django.utils import timezone

    from apps.tenancy.models import SupportSession
    from apps.tenancy.tasks import sweep_support_sessions
    from tests.helpers import make_user

    staff = make_user("support@example.com", roles=("platform_support",)).user
    past = timezone.now() - timedelta(hours=1)
    with tenant_atomic(org.tenant):
        lapsed = SupportSession.objects.create(
            staff_user=staff,
            reason="investigate an issue",
            ticket_ref="T-1",
            requested_at=past - timedelta(minutes=30),
            status=SupportSession.Status.APPROVED,
            starts_at=past - timedelta(minutes=15),
            ends_at=past,
            duration_minutes=15,
        )
    tenant_site(slug="bravo")  # another tenant: nothing to expire there
    assert sweep_support_sessions.delay().get() >= 2
    with tenant_atomic(org.tenant):
        assert SupportSession.objects.get(pk=lapsed.pk).status == "expired"
    assert _clean()
