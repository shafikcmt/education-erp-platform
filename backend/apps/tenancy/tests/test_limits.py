"""Institution / campus limits (Phase 3 M2; ADR-010, Q12): defaults 1/3, overrides, archived
rows don't count, enforcement only inside the tenant transaction, and concurrent creation can
never exceed the limit (the tenant registry row is locked first)."""

from __future__ import annotations

import threading

import pytest
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.core.tenancy import bind_tenant, tenant_atomic
from apps.tenancy.limits import LimitExceeded, assert_capacity, effective_limits
from apps.tenancy.models import Campus, Institution, Tenant
from tests.isolation.threads import in_thread

pytestmark = pytest.mark.django_db


def _institution(code: str) -> Institution:
    assert_capacity("institution")
    return Institution.objects.create(code=code, name=code, institution_type="school")


def test_defaults_and_overrides(tenant_factory):
    ctx = tenant_factory()
    tenant = Tenant.objects.get(pk=ctx.id)
    assert effective_limits(tenant) == {"max_institutions": 1, "max_campuses": 3}
    tenant.limits = {"max_institutions": 4, "max_campuses": "lots", "other": 9}
    assert effective_limits(tenant) == {"max_institutions": 4, "max_campuses": 3}


def test_institution_limit_counts_only_active_rows(tenant_factory):
    ctx = tenant_factory()
    with tenant_atomic(ctx):
        first = _institution("one")
        with pytest.raises(LimitExceeded) as exc:
            _institution("two")
        assert exc.value.kind == "institution" and exc.value.limit == 1
        first.archived_at = timezone.now()
        first.save()
        _institution("two")  # archived institutions don't count


def test_campus_limit_is_per_tenant(tenant_factory):
    ctx = tenant_factory()
    Tenant.objects.filter(pk=ctx.id).update(limits={"max_institutions": 2, "max_campuses": 3})
    with tenant_atomic(ctx):
        insts = [_institution("a"), _institution("b")]
        for i in range(3):
            assert_capacity("campus")
            Campus.objects.create(institution=insts[i % 2], code=f"c{i}", name="C")
        with pytest.raises(LimitExceeded):
            assert_capacity("campus")


def test_capacity_check_needs_the_tenant_transaction(tenant_factory):
    ctx = tenant_factory()
    with bind_tenant(ctx), pytest.raises(PermissionDenied, match="inside tenant_atomic"):
        assert_capacity("institution")


def test_concurrent_creation_never_exceeds_the_limit(committed_tenant_pair):
    """Two transactions race for the last institution slot: exactly one wins (K4 pattern)."""
    ctx = committed_tenant_pair[0]
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker(code: str) -> None:
        def run() -> None:
            try:
                with tenant_atomic(ctx):
                    barrier.wait()
                    _institution(code)
                    result = "created"
            except LimitExceeded:
                result = "limit"
            with lock:
                outcomes.append(result)

        in_thread(run)

    threads = [threading.Thread(target=worker, args=(c,)) for c in ("x", "y")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    def count_and_clean() -> int:
        with tenant_atomic(ctx):
            total = Institution.objects.count()
            Institution.objects.all().delete()
        return total

    assert sorted(outcomes) == ["created", "limit"]
    assert in_thread(count_and_clean) == 1
