"""Primitive-level concurrency tests K1 and K2 (Phase 3 plan §15.3; owner requirement 9).

Both run on real PostgreSQL as ``erp_app`` with committed data. Worker threads use their own
connections outside the test transaction, so every operation is a real transaction; committed
probe rows are deleted afterwards.

* **K1:** 20 threads x 50 operations alternating between tenants. Zero cross-tenant reads or
  writes, and every cross-tenant write attempt is rejected by RLS.
* **K2:** one physical connection reused across transactions for different tenants and the
  platform. The tenant setting is empty outside each transaction and tenant A never sees
  tenant B's data. This is also the gate that any later persistent-connection change (D4)
  must pass.
"""

from __future__ import annotations

import threading
from collections import Counter

import pytest
from django.db import DatabaseError, connection, connections, transaction

from apps.core.ids import new_id
from apps.core.tenancy import TenantContext, current_tenant, tenant_atomic
from tests.isolation.threads import delete_probe_rows, in_thread
from tests.isolation_app.models import ProbeRecord

pytestmark = pytest.mark.django_db

THREADS = 20
OPERATIONS = 50


def _raw_rows() -> list[tuple[str, str]]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT tenant_id::text, name FROM isolation_probe_record")
        return list(cursor.fetchall())


def test_k1_twenty_threads_alternating_tenants_never_cross():
    tenants = [TenantContext(new_id(), slug=s) for s in ("a", "b")]
    ids = {str(t.id) for t in tenants}
    barrier = threading.Barrier(THREADS)
    violations: list[str] = []
    rejected: Counter[str] = Counter()
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker(n: int) -> None:
        try:
            barrier.wait()
            for i in range(OPERATIONS):
                tenant = tenants[(n + i) % 2]
                other = tenants[(n + i + 1) % 2]
                with tenant_atomic(tenant):
                    ProbeRecord.objects.create(name=f"k1-{n}-{i}")
                    orm = set(ProbeRecord.objects.values_list("tenant_id", flat=True))
                    raw = _raw_rows()
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT count(*) FROM isolation_probe_record WHERE tenant_id = %s",
                            [other.id],
                        )
                        foreign = cursor.fetchone()[0]
                    try:
                        with transaction.atomic(), connection.cursor() as cursor:
                            cursor.execute(
                                "INSERT INTO isolation_probe_record "
                                "(id, created_at, updated_at, tenant_id, name) "
                                "VALUES (%s, now(), now(), %s, 'forged')",
                                [new_id(), other.id],
                            )
                    except DatabaseError as exc:
                        if "row-level security" in str(exc):
                            with lock:
                                rejected["cross_write"] += 1
                    problems = []
                    if orm - {tenant.id}:
                        problems.append("orm saw another tenant")
                    if any(tid != str(tenant.id) for tid, _ in raw):
                        problems.append("raw SQL saw another tenant")
                    if foreign:
                        problems.append("explicit foreign query returned rows")
                    if problems:
                        with lock:
                            violations.extend(f"thread {n} op {i}: {p}" for p in problems)
                if current_tenant() is not None:
                    with lock:
                        violations.append(f"thread {n} op {i}: context leaked")
        except BaseException as exc:
            with lock:
                errors.append(exc)
        finally:
            connections.close_all()

    try:
        threads = [threading.Thread(target=worker, args=(n,)) for n in range(THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert violations == []
        assert rejected["cross_write"] == THREADS * OPERATIONS

        def totals() -> dict[str, Counter]:
            out = {}
            for tenant in tenants:
                with tenant_atomic(tenant):
                    out[str(tenant.id)] = Counter(
                        name.rsplit("-", 1)[0]
                        for name in ProbeRecord.objects.values_list("name", flat=True)
                    )
            return out

        per_tenant = in_thread(totals)
        assert set(per_tenant) == ids
        assert sum(sum(c.values()) for c in per_tenant.values()) == THREADS * OPERATIONS
        for counter in per_tenant.values():
            assert sum(counter.values()) == THREADS * OPERATIONS // 2
            assert "forged" not in counter
    finally:
        delete_probe_rows(*tenants)


def test_k2_one_reused_connection_carries_no_tenant_between_transactions():
    a, b = TenantContext(new_id(), slug="a"), TenantContext(new_id(), slug="b")

    def run() -> list[tuple[str, int, str, list[tuple[str, str]]]]:
        steps: list[tuple[str, int, str, list[tuple[str, str]]]] = []

        def outside() -> str:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_setting('app.tenant_id', true)")
                return cursor.fetchone()[0] or ""

        def pid() -> int:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                return int(cursor.fetchone()[0])

        for label, tenant, write in (
            ("A write", a, "a-secret"),
            ("B write", b, "b-secret"),
            ("A read", a, None),
            ("platform read", None, None),
            ("B read", b, None),
            ("A read again", a, None),
        ):
            if tenant is None:
                steps.append((label, pid(), outside(), _raw_rows()))
                continue
            with tenant_atomic(tenant):
                if write:
                    ProbeRecord.objects.create(name=write)
                rows = _raw_rows()
                current = pid()
            steps.append((label, current, outside(), rows))
        return steps

    try:
        steps = in_thread(run)
    finally:
        delete_probe_rows(a, b)
    pids = {pid for _, pid, _, _ in steps}
    assert len(pids) == 1, "the same physical connection must be reused"
    assert all(setting == "" for _, _, setting, _ in steps)
    seen = {label: {name for _, name in rows} for label, _, _, rows in steps}
    assert seen["A write"] == {"a-secret"}
    assert seen["B write"] == {"b-secret"}
    assert seen["A read"] == seen["A read again"] == {"a-secret"}
    assert seen["B read"] == {"b-secret"}
    assert seen["platform read"] == set()
