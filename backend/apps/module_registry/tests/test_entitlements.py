"""Entitlement resolution, snapshot, cache, expiry sweep, plan limits, trial at provisioning
(Phase 4 M3; ADR-052, ADR-054)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.db import connection
from django.utils import timezone

from apps.billing import services
from apps.billing.models import Subscription, SubscriptionItem
from apps.core.tenancy import tenant_atomic
from apps.core.tenancy.exceptions import TenantContextNotApplied
from apps.module_registry import entitlements
from apps.module_registry import services as registry_services
from apps.module_registry.errors import ModuleNotEntitledError
from apps.module_registry.models import Module, ModuleOverride, TenantModule
from apps.module_registry.tasks import sweep_entitlements
from apps.tenancy.limits import effective_limits
from apps.tenancy.models import Tenant

pytestmark = pytest.mark.django_db
REASON = "Signed order form for the pilot"


@pytest.fixture
def plan(admin):
    return services.create_plan(
        actor=admin.user,
        code="starter",
        name="Starter",
        limits={"max_institutions": 2, "max_campuses": 5},
        modules=["academics", "students", "fees"],
    )


def _snapshot(tenant: Any) -> dict[str, tuple[str, bool, str]]:
    with tenant_atomic(tenant):
        return {
            str(r.module_id): (r.source, r.enabled, r.disabled_reason)
            for r in TenantModule.objects.all()
        }


def _enabled(tenant: Any) -> frozenset[str]:
    with tenant_atomic(tenant):
        return entitlements.enabled_modules()


def _platform() -> set[str]:
    """Built platform modules (computed from the catalogue, so new platform modules count)."""
    return {
        code
        for code, m in entitlements._modules().items()
        if m.category == Module.Category.PLATFORM and m.available
    }


def test_without_a_subscription_only_platform_modules_are_enabled(tenant_factory):
    a = tenant_factory(slug="alpha")
    assert _enabled(a) == _platform()
    with tenant_atomic(a):
        assert entitlements.is_entitled("tenancy")
        assert not entitlements.is_entitled("academics")
        with pytest.raises(ModuleNotEntitledError) as caught:
            entitlements.require_module("academics")
    assert caught.value.status_code == 403
    assert caught.value.problem_code == "module_not_entitled"


def test_plan_modules_are_resolved_with_their_dependencies(admin, plan, built, tenant_factory):
    a = tenant_factory(slug="alpha")
    services.assign_plan(actor=admin.user, tenant_id=a.id, plan_code="starter", reason=REASON)
    snap = _snapshot(a)
    for code in ("academics", "students", "fees"):
        assert snap[code] == ("plan", True, ""), code
    assert snap["tenancy"] == ("platform", True, "")
    assert {"academics", "students", "fees"} <= _enabled(a)
    # Hostel needs attendance, which the plan lacks: the dependency is NOT added silently.
    services.create_addon(actor=admin.user, code="hostel_addon", name="Hostel", module="hostel")
    services.add_addon(actor=admin.user, tenant_id=a.id, addon_code="hostel_addon", reason=REASON)
    assert _snapshot(a)["hostel"] == ("addon", False, "missing_dependency")
    assert "attendance" not in _snapshot(a) and "hostel" not in _enabled(a)


def test_modules_that_are_not_built_are_never_enabled(admin, plan, tenant_factory):
    a = tenant_factory(slug="alpha")
    services.assign_plan(actor=admin.user, tenant_id=a.id, plan_code="starter", reason=REASON)
    snap = _snapshot(a)
    assert snap["academics"] == ("plan", True, "")  # built since Phase 6
    assert snap["students"] == ("plan", False, "not_built")
    assert snap["fees"][1] is False  # not built either
    assert _enabled(a) == _platform() | {"academics"}


def test_overrides_grant_and_revoke(admin, plan, built, tenant_factory):
    a = tenant_factory(slug="alpha")
    services.assign_plan(actor=admin.user, tenant_id=a.id, plan_code="starter", reason=REASON)
    registry_services.set_override(
        actor=admin.user, tenant_id=a.id, module_code="students", kind="revoke", reason=REASON
    )
    snap = _snapshot(a)
    assert snap["students"] == ("plan", False, "revoked")
    assert snap["fees"] == ("plan", False, "missing_dependency")  # fees needs students
    registry_services.end_override(
        actor=admin.user, tenant_id=a.id, module_code="students", reason=REASON
    )
    registry_services.set_override(
        actor=admin.user, tenant_id=a.id, module_code="staff", kind="grant", reason=REASON
    )
    snap = _snapshot(a)
    assert snap["fees"] == ("plan", True, "")
    assert snap["staff"] == ("override", True, "")


def test_suspended_or_expired_subscriptions_keep_only_platform_modules(
    admin, plan, built, tenant_factory
):
    a = tenant_factory(slug="alpha")
    services.assign_plan(actor=admin.user, tenant_id=a.id, plan_code="starter", reason=REASON)
    for status in ("suspended", "canceled", "expired"):
        Subscription.objects.filter(tenant_id=a.id).update(status=status)
        assert {c for c, (_, on, _) in entitlements.resolve(a.id).items() if on} == _platform()
    Subscription.objects.filter(tenant_id=a.id).update(status="past_due")
    assert entitlements.resolve(a.id)["fees"][1] is True


def test_plan_changes_invalidate_the_cache_on_the_next_read(admin, plan, built, tenant_factory):
    a = tenant_factory(slug="alpha")
    assert "fees" not in _enabled(a)  # cached now
    services.assign_plan(actor=admin.user, tenant_id=a.id, plan_code="starter", reason=REASON)
    assert "fees" in _enabled(a)
    services.create_plan(actor=admin.user, code="mini", name="Mini", modules=["academics"])
    services.assign_plan(actor=admin.user, tenant_id=a.id, plan_code="mini", reason=REASON)
    assert "fees" not in _enabled(a) and "academics" in _enabled(a)


def test_recompute_and_reads_require_the_tenant_transaction(tenant_factory):
    a, b = tenant_factory(slug="alpha"), tenant_factory(slug="bravo")
    with pytest.raises(Exception, match="tenant"):
        entitlements.recompute(a.id)
    with tenant_atomic(a):
        with pytest.raises(TenantContextNotApplied):
            entitlements.recompute(b.id)
        with pytest.raises(TenantContextNotApplied):
            entitlements.enabled_modules(b.id)


def test_snapshots_are_isolated_per_tenant(admin, plan, built, tenant_factory):
    a, b = tenant_factory(slug="alpha"), tenant_factory(slug="bravo")
    services.assign_plan(actor=admin.user, tenant_id=a.id, plan_code="starter", reason=REASON)
    with tenant_atomic(b):
        entitlements.recompute(b.id)
        assert not TenantModule.objects.filter(module_id="fees").exists()
        with connection.cursor() as cursor:  # raw SQL as erp_app: RLS, not the manager
            cursor.execute(
                "SELECT count(*) FROM module_registry_tenantmodule WHERE tenant_id = %s", [a.id]
            )
            assert cursor.fetchone() == (0,)
    assert "fees" in _enabled(a) and "fees" not in _enabled(b)


# --------------------------------------------------------------------------- P19 sweep
def test_the_sweep_ends_lapsed_trials_addons_and_overrides(admin, plan, built, tenant_factory):
    a, b = tenant_factory(slug="alpha"), tenant_factory(slug="bravo")
    services.start_trial(
        actor=admin.user, tenant_id=a.id, plan_code="starter", days=14, reason=REASON
    )
    services.assign_plan(actor=admin.user, tenant_id=b.id, plan_code="starter", reason=REASON)
    services.create_addon(actor=admin.user, code="staff_addon", name="Staff", module="staff")
    services.add_addon(
        actor=admin.user,
        tenant_id=b.id,
        addon_code="staff_addon",
        reason=REASON,
        valid_until=timezone.now() + timedelta(days=1),
    )
    registry_services.set_override(
        actor=admin.user,
        tenant_id=b.id,
        module_code="students",
        kind="revoke",
        reason=REASON,
        expires_at=timezone.now() + timedelta(days=1),
    )
    assert "fees" in _enabled(a) and "staff" in _enabled(b) and "fees" not in _enabled(b)
    past = timezone.now() - timedelta(minutes=1)
    Subscription.objects.filter(tenant_id=a.id).update(trial_ends_at=past)
    SubscriptionItem.objects.filter(tenant_id=b.id).update(valid_until=past)
    ModuleOverride.objects.filter(tenant_id=b.id).update(expires_at=past)
    assert sweep_entitlements.delay().get() == 2
    assert Subscription.objects.get(tenant_id=a.id).status == "expired"
    assert SubscriptionItem.objects.get(tenant_id=b.id).ended_at is not None
    assert ModuleOverride.objects.get(tenant_id=b.id).ended_at is not None
    assert _enabled(a) == _platform()
    assert "staff" not in _enabled(b) and "fees" in _enabled(b)
    assert sweep_entitlements.delay().get() == 0  # nothing left to end


# --------------------------------------------------------------------------- limits
def test_limits_come_from_the_plan_and_the_override_wins(admin, plan, tenant_factory):
    from apps.tenancy.services.registry import override_limits

    a, b = tenant_factory(slug="alpha"), tenant_factory(slug="bravo")
    without_plan = effective_limits(Tenant.objects.get(pk=b.id))
    assert without_plan == effective_limits(Tenant.objects.get(pk=a.id))  # Phase 3 behaviour
    services.assign_plan(actor=admin.user, tenant_id=a.id, plan_code="starter", reason=REASON)
    assert effective_limits(Tenant.objects.get(pk=a.id)) == {
        "max_institutions": 2,
        "max_campuses": 5,
    }
    override_limits(
        actor=admin.user,
        tenant_id=a.id,
        limits={"max_institutions": 9, "max_campuses": 9},
        reason=REASON,
    )
    assert effective_limits(Tenant.objects.get(pk=a.id)) == {
        "max_institutions": 9,
        "max_campuses": 9,
    }
    assert effective_limits(Tenant.objects.get(pk=b.id)) == without_plan


# --------------------------------------------------------------------------- trial at provisioning
def test_new_tenants_start_on_the_trial_plan_when_it_exists(admin, settings):
    from apps.billing.provisioning import start_trial_plan

    tenant = Tenant.objects.get(pk=_tenant_without_subscription().id)
    start_trial_plan(tenant, admin.user)  # no trial plan yet: nothing happens
    assert not Subscription.objects.filter(tenant_id=tenant.pk).exists()
    trial = services.create_plan(actor=admin.user, code="trial", name="Trial", modules=["fees"])
    start_trial_plan(tenant, admin.user)  # trial plan without trial_days: still nothing
    assert not Subscription.objects.filter(tenant_id=tenant.pk).exists()
    services.update_plan(actor=admin.user, plan=trial, changes={"trial_days": 21})
    from apps.core.tenancy.platform import platform_scope

    with platform_scope(operation="P4", actor=admin.user, reason="provision a test tenant"):
        start_trial_plan(tenant, admin.user)
    sub = Subscription.objects.get(tenant_id=tenant.pk)
    assert (sub.plan.code, sub.status) == ("trial", "trialing")
    assert sub.trial_ends_at is not None
    assert timedelta(days=20) < sub.trial_ends_at - timezone.now() <= timedelta(days=21)
    assert "fees" in _snapshot(tenant.as_context())


def _tenant_without_subscription() -> Any:
    from tests.isolation.factories import make_tenant

    return make_tenant(slug="trialist")
