"""Billing catalogue and subscriptions (Phase 4 M2; ADR-051, ADR-053, ADR-054)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.db.utils import ProgrammingError
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.billing import services
from apps.billing.models import Plan, Price, Subscription, SubscriptionItem
from apps.core.tenancy import tenant_atomic
from apps.module_registry import services as registry_services
from apps.module_registry.models import ModuleOverride
from tests.helpers import make_user
from tests.isolation.factories import tenant_events

pytestmark = pytest.mark.django_db
REASON = "Signed order form for the pilot"


@pytest.fixture
def billing_admin():
    return make_user("billing@example.com", roles=("platform_billing",), mfa=True).user


@pytest.fixture
def plan(admin):
    return services.create_plan(
        actor=admin.user,
        code="starter",
        name="Starter",
        limits={"max_institutions": 1, "max_campuses": 2},
        modules=["academics", "students"],
    )


def test_catalogue_changes_need_the_platform_permission(admin, billing_admin):
    plain = make_user("plain@example.com").user
    support = make_user("support@example.com", roles=("platform_support",)).user
    for actor in (plain, support):
        with pytest.raises(PermissionDenied):
            services.create_plan(actor=actor, code="x_plan", name="X")
    plan = services.create_plan(actor=billing_admin, code="growth", name="Growth", modules=["fees"])
    assert sorted(plan.plan_modules.values_list("module__code", flat=True)) == ["fees"]
    with pytest.raises(ValidationError, match="Platform modules"):
        services.create_plan(actor=admin.user, code="bad_plan", name="Bad", modules=["tenancy"])
    with pytest.raises(ValidationError, match="Unknown modules"):
        services.create_plan(actor=admin.user, code="bad_plan", name="Bad", modules=["nope"])
    with pytest.raises(ValidationError, match="Unknown limit"):
        services.create_plan(actor=admin.user, code="bad_plan", name="Bad", limits={"x": 1})
    with pytest.raises(ValidationError):
        services.create_plan(actor=admin.user, code="growth", name="Again")
    updated = services.update_plan(
        actor=billing_admin, plan=plan, changes={"name": "Growth+"}, modules=["fees", "hostel"]
    )
    assert updated.name == "Growth+"
    changed = AuditEvent.objects.get(action="billing.plan.modules_changed")
    assert changed.metadata == {"plan_code": "growth", "added": ["hostel"], "removed": []}
    addon = services.create_addon(
        actor=billing_admin, code="hostel_addon", name="Hostel", module="hostel"
    )
    assert addon.module_id == "hostel"
    with pytest.raises(ValidationError, match="sellable"):
        services.create_addon(actor=billing_admin, code="core_addon", name="Core", module="core")


def test_prices_are_never_edited_only_replaced(admin, plan):
    first = services.add_price(
        actor=admin.user, plan=plan, currency="BDT", interval="month", amount="1500"
    )
    second = services.add_price(
        actor=admin.user, plan=plan, currency="BDT", interval="month", amount="1750.5"
    )
    first.refresh_from_db()
    assert (first.active, first.amount) == (False, Decimal("1500.00"))
    assert (second.active, second.amount) == (True, Decimal("1750.50"))
    assert Price.objects.filter(plan=plan).count() == 2
    with pytest.raises(ValidationError, match="negative"):
        services.add_price(
            actor=admin.user, plan=plan, currency="BDT", interval="month", amount="-1"
        )
    with pytest.raises(ValidationError, match="exactly one"):
        services.add_price(actor=admin.user, currency="BDT", interval="month", amount="1")
    no_step_up = make_user("billing2@example.com", roles=("platform_billing",), mfa=True).user
    services.deactivate_price(actor=no_step_up, price=second)
    assert Price.objects.filter(plan=plan, active=True).count() == 0
    assert not Plan.objects.filter(code="trial").exists()  # nothing is seeded by code


def test_subscription_changes_write_both_logs_and_tenants_only_read_their_own(
    admin, plan, tenant_factory
):
    a = tenant_factory(slug="alpha")
    b = tenant_factory(slug="bravo")
    with pytest.raises(ValidationError, match="reason"):
        services.assign_plan(actor=admin.user, tenant_id=a.id, plan_code="starter", reason="short")
    trial = services.start_trial(
        actor=admin.user, tenant_id=a.id, plan_code="starter", days=14, reason=REASON
    )
    assert trial.status == Subscription.Status.TRIALING and trial.trial_ends_at
    sub = services.assign_plan(actor=admin.user, tenant_id=a.id, plan_code="starter", reason=REASON)
    assert (sub.status, sub.trial_ends_at) == (Subscription.Status.ACTIVE, None)
    services.assign_plan(actor=admin.user, tenant_id=b.id, plan_code="starter", reason=REASON)
    services.create_addon(actor=admin.user, code="hostel_addon", name="Hostel", module="hostel")
    services.add_addon(actor=admin.user, tenant_id=a.id, addon_code="hostel_addon", reason=REASON)
    with pytest.raises(ValidationError, match="already active"):
        services.add_addon(
            actor=admin.user, tenant_id=a.id, addon_code="hostel_addon", reason=REASON
        )
    assert [
        e.metadata["new"] for e in tenant_events(a, action="billing.subscription.plan_changed")
    ] == ["starter"]
    # Tenant A sees only its own rows and can't write them (ADR-051).
    with tenant_atomic(a):
        assert list(Subscription.objects.values_list("tenant_id", flat=True)) == [a.id]
        assert SubscriptionItem.objects.count() == 1
        with pytest.raises(ProgrammingError), connection.cursor() as cursor:
            cursor.execute("UPDATE billing_subscription SET status = 'active'")
            if cursor.rowcount == 0:
                raise ProgrammingError("no row updated")
    assert Subscription.objects.count() == 2  # the platform sees both
    assert (
        services.remove_addon(
            actor=admin.user, tenant_id=a.id, addon_code="hostel_addon", reason=REASON
        )
        == 1
    )


def test_tenant_context_cannot_insert_billing_rows(admin, plan, tenant_factory):
    a = tenant_factory(slug="alpha")
    with tenant_atomic(a), pytest.raises(ProgrammingError, match="row-level security"):
        Subscription.objects.create(tenant_id=a.id, plan=plan)


def test_module_overrides_need_step_up_permission_and_end_cleanly(admin, tenant_factory):
    a = tenant_factory(slug="alpha")
    billing_viewer = make_user("viewer@example.com", roles=("platform_support",)).user
    with pytest.raises(PermissionDenied):
        registry_services.set_override(
            actor=billing_viewer, tenant_id=a.id, module_code="hostel", kind="grant", reason=REASON
        )
    with pytest.raises(ValidationError, match="non-platform"):
        registry_services.set_override(
            actor=admin.user, tenant_id=a.id, module_code="tenancy", kind="grant", reason=REASON
        )
    with pytest.raises(ValidationError, match="future"):
        registry_services.set_override(
            actor=admin.user,
            tenant_id=a.id,
            module_code="hostel",
            kind="grant",
            reason=REASON,
            expires_at=timezone.now() - timedelta(days=1),
        )
    registry_services.set_override(
        actor=admin.user, tenant_id=a.id, module_code="hostel", kind="grant", reason=REASON
    )
    registry_services.set_override(
        actor=admin.user, tenant_id=a.id, module_code="hostel", kind="revoke", reason=REASON
    )
    open_ones = ModuleOverride.objects.filter(tenant_id=a.id, ended_at__isnull=True)
    assert [o.kind for o in open_ones] == ["revoke"]
    assert (
        registry_services.end_override(
            actor=admin.user, tenant_id=a.id, module_code="hostel", reason=REASON
        )
        == 1
    )
    assert len(tenant_events(a, action="module_registry.override.set")) == 2


def test_feature_flags_are_data_only(admin, tenant_factory):
    a, b = tenant_factory(slug="alpha"), tenant_factory(slug="bravo")
    with pytest.raises(ValidationError, match="Unknown rule"):
        registry_services.set_flag(
            actor=admin.user, key="new.dashboard", default_enabled=False, rules={"x": 1}
        )
    with pytest.raises(ValidationError, match="0-100"):
        registry_services.set_flag(
            actor=admin.user, key="new.dashboard", default_enabled=False, rules={"percentage": 101}
        )
    registry_services.set_flag(
        actor=admin.user,
        key="new.dashboard",
        default_enabled=False,
        rules={"tenants": [str(a.id)], "plans": ["growth"]},
    )
    assert registry_services.flag_enabled("new.dashboard", tenant_id=a.id) is True
    assert registry_services.flag_enabled("new.dashboard", tenant_id=b.id) is False
    assert (
        registry_services.flag_enabled("new.dashboard", tenant_id=b.id, plan_code="growth") is True
    )
    assert registry_services.flag_enabled("missing.flag", tenant_id=a.id) is False
    registry_services.set_flag(
        actor=admin.user, key="half.rollout", default_enabled=False, rules={"percentage": 100}
    )
    assert registry_services.flag_enabled("half.rollout", tenant_id=b.id) is True
    with pytest.raises(PermissionDenied):
        registry_services.set_flag(
            actor=make_user("p@example.com").user, key="x.flag", default_enabled=True
        )
