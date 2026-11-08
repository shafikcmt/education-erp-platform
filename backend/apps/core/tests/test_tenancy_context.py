"""Python-side tenant context (Phase 3 M1): validation, binding, thread and asyncio isolation."""

import asyncio
import threading
import uuid

import pytest

from apps.core.ids import new_id
from apps.core.tenancy import (
    InvalidTenantId,
    TenantContext,
    TenantContextConflict,
    TenantContextMissing,
    bind_tenant,
    current_tenant,
    require_tenant,
    validate_tenant_id,
)


def test_accepts_uuidv7_and_its_canonical_string():
    tid = new_id()
    assert validate_tenant_id(tid) == tid
    assert validate_tenant_id(str(tid)) == tid


@pytest.mark.parametrize(
    "value",
    [
        uuid.UUID(int=0),  # nil
        uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),  # max
        uuid.uuid4(),  # wrong version
        "not-a-uuid",
        "",
        None,
        12345,
        b"\x00" * 16,
    ],
)
def test_rejects_non_uuidv7_values(value):
    with pytest.raises(InvalidTenantId):
        validate_tenant_id(value)


def test_rejects_non_canonical_strings():
    tid = str(new_id())
    for loose in (tid.upper(), "{" + tid + "}", "urn:uuid:" + tid, tid.replace("-", ""), f" {tid}"):
        with pytest.raises(InvalidTenantId):
            validate_tenant_id(loose)


def test_tenant_context_is_frozen_validated_and_coercible():
    tid = new_id()
    ctx = TenantContext(id=tid, slug="acme", status="active")
    with pytest.raises(AttributeError):
        ctx.id = new_id()  # type: ignore[misc]
    with pytest.raises(InvalidTenantId):
        TenantContext(id=uuid.uuid4())
    assert TenantContext.coerce(ctx) is ctx
    assert TenantContext.coerce(str(tid)).id == tid


def test_require_tenant_fails_closed():
    assert current_tenant() is None
    with pytest.raises(TenantContextMissing):
        require_tenant()


def test_bind_restores_after_success_and_failure():
    tid = new_id()
    with bind_tenant(tid) as ctx:
        assert require_tenant() == ctx
    assert current_tenant() is None
    with pytest.raises(RuntimeError), bind_tenant(tid):
        raise RuntimeError("boom")
    assert current_tenant() is None


def test_rebinding_same_tenant_is_allowed_and_different_tenant_conflicts():
    a, b = new_id(), new_id()
    with bind_tenant(a):
        with bind_tenant(a):
            assert require_tenant().id == a
        with pytest.raises(TenantContextConflict), bind_tenant(b):
            pass
        assert require_tenant().id == a
    assert current_tenant() is None


def test_threads_never_see_each_others_context():
    seen: dict[int, list[object]] = {}
    barrier = threading.Barrier(8)

    def work(n: int) -> None:
        tid = new_id()
        out = seen.setdefault(n, [])
        out.append(current_tenant())  # nothing inherited from the main thread
        with bind_tenant(tid):
            barrier.wait()
            for _ in range(200):
                ctx = current_tenant()
                assert ctx is not None
                out.append(ctx.id if ctx.id == tid else None)
        out.append(current_tenant())

    with bind_tenant(new_id()):
        threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    for values in seen.values():
        assert values[0] is None and values[-1] is None
        assert None not in values[1:-1]


def test_asyncio_tasks_never_see_each_others_context():
    async def work(tid: uuid.UUID) -> list[bool]:
        results = []
        with bind_tenant(tid):
            for _ in range(50):
                await asyncio.sleep(0)  # force interleaving between tasks
                results.append(require_tenant().id == tid)
        results.append(current_tenant() is None)
        return results

    async def main() -> list[list[bool]]:
        return await asyncio.gather(*(work(new_id()) for _ in range(10)))

    assert all(all(r) for r in asyncio.run(main()))
    assert current_tenant() is None


def test_core_db_tenant_atomic_is_the_same_single_helper():
    from apps.core import db
    from apps.core.tenancy import transaction

    assert db.tenant_atomic is transaction.tenant_atomic
