"""``tenant_atomic`` and the query guard (Phase 3 M1; plan §8.1, §8.3, §8.5).

Tests on the main thread run inside pytest-django's test transaction (on every alias), so they
exercise the "inside an enclosing transaction" path. Tests that need real COMMIT/ROLLBACK,
``on_commit`` and connection reuse run in a worker thread with its own unwrapped connection
(``tests.isolation.threads.in_thread``) and clean up committed rows afterwards.
"""

import contextvars
import logging
import threading
import uuid

import pytest
from django.core.signals import request_finished
from django.db import DatabaseError, connection, connections, transaction
from django.test.utils import CaptureQueriesContext

from apps.core.ids import new_id
from apps.core.tenancy import (
    InvalidTenantId,
    TenantContext,
    TenantContextConflict,
    TenantContextLeak,
    TenantContextMissing,
    TenantContextNotApplied,
    bind_tenant,
    boundaries,
    current_tenant,
    tenant_atomic,
)
from apps.core.tenancy import context as ctx_module
from apps.core.tenancy.transaction import (
    _STATE_ATTR,
    _TxState,
    applied_tenant_id,
    has_query_guard,
)
from tests.isolation.threads import in_thread
from tests.isolation_app.models import ProbeRecord

SECONDARY = "isolation_secondary"
pytestmark = pytest.mark.django_db(databases=["default", SECONDARY])


def _setting(alias: str = "default") -> str:
    with connections[alias].cursor() as cursor:
        cursor.execute("SELECT current_setting('app.tenant_id', true)")
        return cursor.fetchone()[0] or ""


def _pid(alias: str) -> int:
    with connections[alias].cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        return int(cursor.fetchone()[0])


@pytest.fixture
def a(tenant_factory) -> TenantContext:
    ctx: TenantContext = tenant_factory()
    return ctx


@pytest.fixture
def b(tenant_factory) -> TenantContext:
    ctx: TenantContext = tenant_factory()
    return ctx


# --------------------------------------------------------------------------- applying
def test_applies_transaction_local_setting_and_restores(a):
    assert _setting() == ""
    with tenant_atomic(a) as ctx:
        assert ctx == a and current_tenant() == a
        assert _setting() == str(a.id)
        assert applied_tenant_id(connection) == a.id
    assert current_tenant() is None
    assert applied_tenant_id(connection) is None
    assert _setting() == ""  # cleared inside the enclosing (test) transaction too


def test_first_statement_applies_the_tenant(a):
    with CaptureQueriesContext(connection) as captured, tenant_atomic(a):
        pass
    statements = [
        q["sql"]
        for q in captured.captured_queries
        if not q["sql"].startswith(("SAVEPOINT", "RELEASE"))
    ]
    assert statements[0] == f"SELECT pg_catalog.set_config('app.tenant_id', '{a.id}', true)"
    assert all("set_config" not in s or "true)" in s for s in statements)


def test_needs_a_tenant_and_validates_it():
    with pytest.raises(TenantContextMissing), tenant_atomic():
        pass
    with pytest.raises(InvalidTenantId), tenant_atomic(uuid.uuid4()):
        pass
    with pytest.raises(InvalidTenantId), tenant_atomic("garbage"):
        pass
    with (
        pytest.raises(TenantContextConflict, match="Unknown database alias"),
        tenant_atomic(new_id(), using="nope"),
    ):
        pass


def test_uses_the_bound_tenant_when_none_is_given(a):
    with bind_tenant(a), tenant_atomic() as ctx:
        assert ctx == a and _setting() == str(a.id)


# --------------------------------------------------------------------------- nesting
def test_nested_same_tenant_uses_a_savepoint_and_keeps_the_setting(a):
    with tenant_atomic(a):
        with CaptureQueriesContext(connection) as captured, tenant_atomic(a):
            assert _setting() == str(a.id)
        assert any(q["sql"].startswith("SAVEPOINT") for q in captured.captured_queries)
        assert not any("set_config" in q["sql"] for q in captured.captured_queries)
        assert _setting() == str(a.id) and current_tenant() == a


def test_nested_different_tenant_raises_and_outer_is_untouched(a, b):
    with tenant_atomic(a):
        with pytest.raises(TenantContextConflict), tenant_atomic(b):
            pass
        assert current_tenant() == a and _setting() == str(a.id)
    with bind_tenant(a), pytest.raises(TenantContextConflict), tenant_atomic(b):
        pass


# --------------------------------------------------------------------------- rollback
def test_exception_rolls_back_rows_and_setting(a):
    with pytest.raises(RuntimeError), tenant_atomic(a):
        ProbeRecord.objects.create(name="doomed")
        raise RuntimeError("boom")
    assert current_tenant() is None and _setting() == ""
    with tenant_atomic(a):
        assert not ProbeRecord.objects.filter(name="doomed").exists()


def test_inner_savepoint_rollback_keeps_outer_work_and_tenant(a):
    with tenant_atomic(a):
        ProbeRecord.objects.create(name="kept")
        with pytest.raises(RuntimeError), transaction.atomic():
            ProbeRecord.objects.create(name="rolled-back")
            raise RuntimeError("inner")
        assert _setting() == str(a.id)
        assert set(ProbeRecord.objects.values_list("name", flat=True)) == {"kept"}


def test_on_commit_runs_after_commit_and_never_after_rollback(committed_tenant_pair):
    a = committed_tenant_pair[0]

    def run() -> list[str]:
        calls: list[str] = []
        with tenant_atomic(a):
            ProbeRecord.objects.create(name="committed")
            transaction.on_commit(lambda: calls.append("committed"))
        with pytest.raises(RuntimeError), tenant_atomic(a):
            ProbeRecord.objects.create(name="rolled-back")
            transaction.on_commit(lambda: calls.append("rolled-back"))
            raise RuntimeError("boom")
        with tenant_atomic(a):
            calls.extend(ProbeRecord.objects.values_list("name", flat=True))
        return calls

    assert in_thread(run) == ["committed", "committed"]


def test_on_commit_callbacks_cannot_query_tenant_data(committed_tenant_pair):
    a = committed_tenant_pair[0]

    def run() -> list[BaseException]:
        errors: list[BaseException] = []

        def callback() -> None:
            try:
                ProbeRecord.objects.count()
            except BaseException as exc:
                errors.append(exc)

        with tenant_atomic(a):
            transaction.on_commit(callback)
        return errors

    errors = in_thread(run)
    assert len(errors) == 1 and isinstance(errors[0], TenantContextNotApplied)


def test_committed_transaction_leaves_nothing_on_the_reused_connection(committed_tenant_pair):
    a, b = committed_tenant_pair

    def run() -> tuple[int, int, str, int, int, str]:
        with tenant_atomic(a):
            ProbeRecord.objects.create(name="a-row")
            pid_a = _pid("default")
        after_a = _setting()
        with tenant_atomic(b):
            pid_b = _pid("default")
            orm = ProbeRecord.objects.count()
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM isolation_probe_record")
                raw = cursor.fetchone()[0]
        return pid_a, pid_b, after_a, orm, raw, _setting()

    pid_a, pid_b, after_a, orm, raw, after_b = in_thread(run)
    assert pid_a == pid_b  # same physical connection reused
    assert after_a == "" and after_b == ""
    assert orm == 0 and raw == 0  # RLS, not only the manager


# --------------------------------------------------------------------------- query guard
def test_every_connection_has_the_guard():
    assert has_query_guard(connections["default"])
    connections[SECONDARY].ensure_connection()
    assert has_query_guard(connections[SECONDARY])


def test_a_bound_context_alone_never_lets_queries_through(a):
    with bind_tenant(a):
        with pytest.raises(TenantContextNotApplied):
            ProbeRecord.objects.count()
        with pytest.raises(TenantContextNotApplied), connection.cursor() as cursor:
            cursor.execute("SELECT 1")


def test_guard_tracks_each_alias_separately(a, b):
    with tenant_atomic(a):
        with pytest.raises(TenantContextNotApplied):
            ProbeRecord.objects.using(SECONDARY).count()
        with tenant_atomic(a, using=SECONDARY):
            assert ProbeRecord.objects.using(SECONDARY).count() == 0
            assert _setting(SECONDARY) == str(a.id)
        with pytest.raises(TenantContextConflict), tenant_atomic(b, using=SECONDARY):
            pass
    assert _setting(SECONDARY) == ""


def test_guard_detects_connection_state_without_context(a):
    setattr(connection, _STATE_ATTR, _TxState(a.id, 1, True))
    try:
        with pytest.raises(TenantContextLeak), connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    finally:
        setattr(connection, _STATE_ATTR, None)


def test_stale_state_is_never_reused(a):
    def run() -> None:
        connection.ensure_connection()
        setattr(connection, _STATE_ATTR, _TxState(a.id, 1, False))  # outside any transaction
        try:
            with tenant_atomic(a):
                pass
        finally:
            setattr(connection, _STATE_ATTR, None)

    with pytest.raises(TenantContextLeak, match="Stale"):
        in_thread(run)


def test_new_threads_inherit_nothing(a):
    with tenant_atomic(a):
        ProbeRecord.objects.create(name="in-main-transaction")
        results: dict[str, object] = {}

        def plain() -> None:
            try:
                results["ctx"] = current_tenant()
                with connections["default"].cursor() as cursor:
                    cursor.execute("SELECT count(*) FROM isolation_probe_record")
                    results["rows"] = cursor.fetchone()[0]
            finally:
                connections.close_all()

        def copied() -> None:
            try:
                with connections["default"].cursor() as cursor:
                    cursor.execute("SELECT 1")
            except TenantContextNotApplied as exc:
                results["copied"] = exc
            finally:
                connections.close_all()

        t1 = threading.Thread(target=plain)
        t1.start()
        t1.join()
        snapshot = contextvars.copy_context()
        t2 = threading.Thread(target=snapshot.run, args=(copied,))
        t2.start()
        t2.join()
    assert results["ctx"] is None and results["rows"] == 0
    assert isinstance(results["copied"], TenantContextNotApplied)


# --------------------------------------------------------------------------- boundaries
def test_request_boundary_detects_and_clears_a_leaked_context(a, caplog):
    ctx_module._CURRENT.set(a)  # simulate code that bound a tenant without restoring it
    with (
        caplog.at_level(logging.ERROR, logger="apps.core.tenancy"),
        pytest.raises(TenantContextLeak),
    ):
        request_finished.send(sender=None)
    assert current_tenant() is None
    assert any(r.getMessage() == "tenancy.context_leak" for r in caplog.records)


def test_celery_boundary_clears_leaks_before_and_after_a_task(a, caplog):
    from apps.core.tasks import ping

    ctx_module._CURRENT.set(a)
    with caplog.at_level(logging.ERROR, logger="apps.core.tenancy"):
        ping.delay()  # eager in tests; Celery signals log receiver errors instead of raising
    assert current_tenant() is None
    assert [r for r in caplog.records if r.getMessage() == "tenancy.context_leak"]


def test_boundary_is_silent_when_clean(caplog):
    with caplog.at_level(logging.ERROR, logger="apps.core.tenancy"):
        boundaries.check_boundary("test")
    assert not caplog.records


def test_requests_run_without_tenant_state(client):
    assert client.get("/healthz").status_code == 200
    assert current_tenant() is None


def test_database_errors_inside_still_restore_state(a):
    with pytest.raises(DatabaseError), tenant_atomic(a), connection.cursor() as cursor:
        cursor.execute("SELECT * FROM table_that_does_not_exist")
    assert current_tenant() is None and applied_tenant_id(connection) is None


def test_boundary_clears_leaked_platform_operation_and_connection_state(a):
    from apps.core.tenancy.platform import CATALOGUE, PlatformOperation

    ctx_module._PLATFORM_OPERATION.set(
        PlatformOperation(spec=CATALOGUE["P10"], actor=None, reason="x", permission=None)
    )
    connection.ensure_connection()
    setattr(connection, _STATE_ATTR, _TxState(a.id, 1, True))
    with pytest.raises(TenantContextLeak):
        boundaries.check_boundary("test")
    assert ctx_module._PLATFORM_OPERATION.get() is None
    assert getattr(connection, _STATE_ATTR) is None


# --------------------------------------------------------------------------- M3: lock_timeout
def _lock_timeout() -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('lock_timeout')")
        return str(cursor.fetchone()[0])


def test_lock_timeout_is_transaction_local(tenant_factory):
    tenant = tenant_factory()
    before = _lock_timeout()
    with tenant_atomic(tenant, lock_timeout="5s"):
        assert _lock_timeout() == "5s"
        with tenant_atomic(tenant, lock_timeout="1s"):  # nested: the outer limit stays
            assert _lock_timeout() == "5s"
    assert _lock_timeout() == before
    with tenant_atomic(tenant):
        assert _lock_timeout() == before


@pytest.mark.parametrize("value", ["", "5", "5 s", "0s", "5s; DROP TABLE x", "1h", "-1s", "abc"])
def test_lock_timeout_accepts_only_simple_durations(tenant_factory, value):
    with (
        pytest.raises(ValueError, match="lock_timeout"),
        tenant_atomic(tenant_factory(), lock_timeout=value),
    ):
        pass


def test_marked_for_rollback_block_inside_an_outer_transaction_restores_everything(
    tenant_factory,
):
    """A request that ends with ``set_rollback(True)`` inside an enclosing transaction (the
    test transaction): the savepoint rollback discards the data and both settings, and the
    outer transaction stays usable."""
    tenant = tenant_factory()
    before = _lock_timeout()
    with tenant_atomic(tenant, lock_timeout="5s"):
        ProbeRecord.objects.create(name="discarded")
        transaction.set_rollback(True)
    assert not connection.needs_rollback
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.tenant_id', true)")
        assert (cursor.fetchone()[0] or "") == ""
    assert _lock_timeout() == before
    with tenant_atomic(tenant):
        assert not ProbeRecord.objects.exists()


def test_lock_timeout_stops_a_blocked_request(committed_tenant_pair):
    """Two real transactions: the second gives up after its lock wait limit instead of
    hanging behind the first."""
    import threading

    from django.db import OperationalError

    from tests.isolation.threads import in_thread

    tenant, _ = committed_tenant_pair
    in_thread(lambda: _create_probe(tenant, "locked-row"))
    holding, release = threading.Event(), threading.Event()

    def holder() -> None:
        with tenant_atomic(tenant):
            list(ProbeRecord.objects.select_for_update())
            holding.set()
            release.wait(timeout=10)

    def waiter() -> str:
        holding.wait(timeout=10)
        try:
            with tenant_atomic(tenant, lock_timeout="200ms"):
                list(ProbeRecord.objects.select_for_update())
        except OperationalError as exc:
            return str(exc)
        finally:
            release.set()
        return "no timeout"

    thread = threading.Thread(target=lambda: in_thread(holder))
    thread.start()
    try:
        message = in_thread(waiter)
    finally:
        release.set()
        thread.join()
    assert "lock timeout" in message


def _create_probe(tenant, name: str) -> None:
    with tenant_atomic(tenant):
        ProbeRecord.objects.create(name=name)
