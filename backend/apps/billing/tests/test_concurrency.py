"""Concurrency of subscription changes (Phase 4 plan §8): changes for one tenant serialise on
the subscription row lock, and the stored snapshot always matches the final plan. Real,
committed transactions in worker threads; every committed row is removed afterwards."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from apps.billing import services
from apps.billing.models import Plan, PlanModule, Subscription, SubscriptionItem
from apps.core.tenancy import tenant_atomic
from apps.module_registry.models import TenantModule
from tests.helpers import make_user
from tests.isolation.threads import in_thread

pytestmark = pytest.mark.django_db
REASON = "Concurrency check of plan changes"
PLANS = {"k_plan_a": ["academics"], "k_plan_b": ["fees"], "k_plan_c": ["hostel"]}


def _run_both(first: Any, second: Any) -> None:
    """Run two workers at once; any worker error fails the test (never swallowed)."""
    errors: list[BaseException] = []

    def guarded(fn: Any) -> None:
        try:
            in_thread(fn)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=guarded, args=(fn,)) for fn in (first, second)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors:
        raise errors[0]


def test_subscription_changes_serialise_and_the_snapshot_matches_the_final_plan(
    committed_tenant_pair,
):
    from apps.identity.models import User

    tenant = committed_tenant_pair[0]
    email = f"k-billing-{tenant.id.hex[:8]}@example.com"

    def setup() -> Any:
        admin = make_user(email, roles=("super_admin",), mfa=True).user
        for code, modules in PLANS.items():
            services.create_plan(actor=admin, code=code, name=code, modules=modules)
        services.assign_plan(actor=admin, tenant_id=tenant.id, plan_code="k_plan_a", reason=REASON)
        return admin

    def snapshot_plan_modules() -> set[str]:
        with tenant_atomic(tenant):
            rows = TenantModule.objects.filter(source="plan").values_list("module_id", flat=True)
            return {str(code) for code in rows}

    def cleanup() -> None:
        with tenant_atomic(tenant):
            TenantModule.objects.all().delete()
        SubscriptionItem.objects.filter(tenant_id=tenant.id).delete()
        Subscription.objects.filter(tenant_id=tenant.id).delete()
        PlanModule.objects.filter(plan__code__in=PLANS).delete()
        Plan.objects.filter(code__in=PLANS).delete()
        User.objects.filter(email=email).delete()

    admin = in_thread(setup)
    try:
        # 1. A change waits for a transaction that holds the subscription row.
        barrier = threading.Barrier(2)
        timings: dict[str, float] = {}

        def holder() -> None:
            from django.db import transaction

            with transaction.atomic():
                Subscription.objects.select_for_update().get(tenant_id=tenant.id)
                barrier.wait()
                time.sleep(0.8)

        def changer() -> None:
            barrier.wait()
            started = time.monotonic()
            services.assign_plan(
                actor=admin, tenant_id=tenant.id, plan_code="k_plan_b", reason=REASON
            )
            timings["waited"] = time.monotonic() - started

        _run_both(holder, changer)
        assert timings["waited"] >= 0.6
        assert in_thread(snapshot_plan_modules) == {"fees"}

        # 2. Two racing changes: one wins last, and the snapshot is exactly its modules.
        race = threading.Barrier(2)

        def assign(code: str) -> Any:
            def run() -> None:
                race.wait()
                services.assign_plan(
                    actor=admin, tenant_id=tenant.id, plan_code=code, reason=REASON
                )

            return run

        _run_both(assign("k_plan_a"), assign("k_plan_c"))

        def final_plan() -> str:
            return Subscription.objects.select_related("plan").get(tenant_id=tenant.id).plan.code

        winner = in_thread(final_plan)
        assert winner in {"k_plan_a", "k_plan_c"}
        assert in_thread(snapshot_plan_modules) == set(PLANS[winner])
    finally:
        in_thread(cleanup)
