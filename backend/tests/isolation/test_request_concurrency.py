"""Request-level concurrency and reuse (Phase 3 M3; plan §8.5 L1, L3, L9 and §15.3 K1, K2, K8).

Real HTTP requests through the full middleware stack, in worker threads with their own
connections outside the test transaction, on real PostgreSQL as ``erp_app`` with committed
tenants. Every tenant request therefore runs a real ``BEGIN ... COMMIT``.

**Forced-reuse mode:** the Django test client keeps a thread's database connection open
between requests (it disconnects ``close_old_connections``), so each thread serves all of its
requests on ONE physical connection. That is the persistent-connection case D4 guards against,
which production (``CONN_MAX_AGE = 0``) never even enters; ``pg_backend_pid()`` is asserted to
prove the reuse. The same tests are the gate for any later persistent-connection change.

K3 (the same through Nginx and Uvicorn) is an M10 deliverable. L9 is covered here in process,
through Django's ASGI handler.
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

import pytest
from asgiref.sync import sync_to_async
from django.db import connection, connections
from django.test import AsyncClient, Client

from apps.core.tenancy import current_tenant
from apps.core.tenancy.transaction import connections_with_tenant_state
from tests.isolation.factories import tenant_host
from tests.isolation.threads import in_thread

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])

THREADS = 20
REQUESTS = 50


def _post(client: Client, tenant: Any, name: str) -> Any:
    return client.post(
        "/_probe/records/",
        json.dumps({"name": name}),
        content_type="application/json",
        HTTP_HOST=tenant_host(tenant),
    )


def _between_requests() -> tuple[str, int, bool]:
    """State of this thread's connection outside any request."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.tenant_id', true), pg_backend_pid()")
        setting, pid = cursor.fetchone()
    return setting or "", pid, connection.in_atomic_block


def test_k1_twenty_threads_alternating_three_tenant_hosts(committed_tenant_sites):
    tenants = committed_tenant_sites
    barrier = threading.Barrier(THREADS)
    problems: list[str] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def owner_of(name: str) -> int:
        _, n, i = name.split("-")
        return (int(n) + int(i)) % 3

    def worker(n: int) -> None:
        client = Client()
        try:
            barrier.wait()
            for i in range(REQUESTS):
                tenant = tenants[(n + i) % 3]
                name = f"k1-{n}-{i}"
                created = _post(client, tenant, name)
                listed = client.get("/_probe/records/", HTTP_HOST=tenant_host(tenant)).json()
                with lock:
                    if created.status_code != 201:
                        problems.append(f"create {created.status_code}")
                    if listed["setting"] != str(tenant.id) or listed["raw"] != [str(tenant.id)]:
                        problems.append(f"saw {listed['raw']} as {tenant.slug}")
                    if name not in listed["names"]:
                        problems.append(f"own write missing on {tenant.slug}")
                    if {owner_of(seen) for seen in listed["names"]} != {(n + i) % 3}:
                        problems.append(f"foreign names on {tenant.slug}")
                if current_tenant() is not None or connections_with_tenant_state():
                    problems.append("context leaked after a request")
        except BaseException as exc:
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert problems == []
    # Every write landed in exactly its own tenant, and nothing was lost.
    total = 0
    for index, tenant in enumerate(tenants):
        names = in_thread(
            lambda t=tenant: (
                Client().get("/_probe/records/", HTTP_HOST=tenant_host(t)).json()["names"]
            )
        )
        assert {owner_of(name) for name in names} == {index}
        total += len(names)
    assert total == THREADS * REQUESTS


def test_k2_one_reused_connection_serves_a_b_a_platform_b(committed_tenant_sites):
    """Also L1 and L3: nothing of one request reaches the next on the same connection."""
    a, b, _ = committed_tenant_sites

    def run() -> list[dict[str, Any]]:
        client = Client()
        steps: list[dict[str, Any]] = []
        assert _post(client, a, "k2-a").status_code == 201
        assert _post(client, b, "k2-b").status_code == 201
        for target in (a, b, a, None, b):
            host = tenant_host(target) if target else "testserver"
            body = client.get("/_probe/whoami/", HTTP_HOST=host).json()
            if target is not None:
                body["names"] = client.get("/_probe/records/", HTTP_HOST=host).json()["names"]
            setting, pid, in_tx = _between_requests()
            steps.append({**body, "between": (setting, in_tx), "between_pid": pid})
        return steps

    steps = in_thread(run)
    pids = {step["pid"] for step in steps} | {step["between_pid"] for step in steps}
    assert len(pids) == 1, "the connection must be physically reused"
    expected = [a, b, a, None, b]
    for step, target in zip(steps, expected, strict=True):
        assert step["between"] == ("", False)  # no tenant, no open transaction
        if target is None:
            assert (step["host_kind"], step["setting"], step["raw"]) == ("platform", "", [])
        else:
            assert step["setting"] == step["tenant"] == str(target.id)
            assert step["raw"] == [str(target.id)]
            assert step["names"] == [f"k2-{'a' if target is a else 'b'}"]


def test_k8_platform_requests_interleaved_with_tenant_requests(committed_tenant_sites):
    tenants = committed_tenant_sites
    problems: list[str] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def worker(n: int) -> None:
        client = Client()
        try:
            barrier.wait()
            for i in range(30):
                tenant = tenants[(n + i) % 3]
                if _post(client, tenant, f"k8-{n}-{i}").status_code != 201:
                    problems.append("create failed")
                platform = client.get("/_probe/whoami/", HTTP_HOST="testserver").json()
                if platform["raw"] or platform["setting"] or platform["context"]:
                    problems.append(f"platform request saw {platform}")
                if client.get("/_probe/records/", HTTP_HOST="testserver").status_code != 404:
                    problems.append("tenant-only view served on the platform host")
        except BaseException as exc:
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == [] and problems == []


def test_l9_concurrent_asgi_requests_keep_their_own_tenant(committed_tenant_sites):
    """Django's ASGI handler runs the (sync) middleware chain for many in-flight requests;
    each must keep its own tenant context."""
    tenants = committed_tenant_sites

    async def one(n: int) -> str:
        tenant = tenants[n % 3]
        client = AsyncClient()
        # The async test client always sends ``Host: testserver``; the tenant host travels in
        # the trusted proxy header, exactly as it does from Nginx and the Next.js server.
        via = {"x-forwarded-host": tenant_host(tenant)}
        created = await client.post(
            "/_probe/records/",
            json.dumps({"name": f"l9-{n}"}),
            content_type="application/json",
            headers=via,
        )
        listed = (await client.get("/_probe/records/", headers=via)).json()
        platform = (await client.get("/_probe/whoami/")).json()
        ok = (
            created.status_code == 201
            and listed["setting"] == str(tenant.id)
            and listed["raw"] == [str(tenant.id)]
            and all(name.startswith("l9-") for name in listed["names"])
            and {int(name[3:]) % 3 for name in listed["names"]} == {n % 3}
            and (platform["raw"], platform["setting"], platform["context"]) == ([], "", None)
        )
        return "" if ok else f"request {n} on {tenant.slug}: {listed} / {platform}"

    async def main() -> list[str]:
        try:
            return [p for p in await asyncio.gather(*(one(n) for n in range(60))) if p]
        finally:
            await sync_to_async(connections.close_all)()

    assert in_thread(lambda: asyncio.run(main())) == []
