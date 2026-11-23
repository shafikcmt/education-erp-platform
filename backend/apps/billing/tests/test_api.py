"""Billing and module registry API (Phase 4 M5; plan §6): platform catalogue and tenant
subscription management (allowed and denied), the tenant's own subscription page, and the
entitlements in ``/me/context/``."""

from __future__ import annotations

import uuid

import pytest

from apps.billing import services
from apps.billing.models import Price
from tests.helpers import Api, make_user
from tests.isolation.factories import grant_role, tenant_host

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])
V1 = "/api/v1"
REASON = "Signed order form for the pilot"


def _staff(email: str, *roles: str, step_up: bool = True) -> Api:
    person = make_user(email, roles=roles, mfa=True)
    api = Api()
    api.login(person, expect="authenticated")
    if step_up:
        api.step_up(person)
    return api


def _plan_body(code: str = "starter") -> dict:
    return {
        "code": code,
        "name": "Starter",
        "limits": {"max_institutions": 2, "max_campuses": 4},
        "modules": ["academics", "students"],
        "trial_days": 14,
    }


def test_catalogue_endpoints_follow_the_permissions():
    billing = _staff("billing@example.com", "platform_billing")
    support = _staff("support@example.com", "platform_support")
    plain = Api()
    plain.login(make_user("plain@example.com"), expect="authenticated")

    created = billing.post(f"{V1}/platform/plans/", _plan_body())
    assert created.status_code == 201, created.content
    assert created.json()["modules"] == ["academics", "students"]
    assert created.json()["trial_days"] == 14
    for api in (support, plain):
        assert api.get(f"{V1}/platform/plans/").status_code == 403
        assert api.post(f"{V1}/platform/plans/", _plan_body("other")).status_code == 403
    assert [p["code"] for p in billing.get(f"{V1}/platform/plans/").json()] == ["starter"]
    patched = billing.patch(
        f"{V1}/platform/plans/starter/", {"name": "Starter+", "modules": ["fees"]}
    )
    assert patched.status_code == 200, patched.content
    assert (patched.json()["name"], patched.json()["modules"]) == ("Starter+", ["fees"])
    assert billing.get(f"{V1}/platform/plans/nope/").status_code == 404
    bad = billing.post(f"{V1}/platform/plans/", {**_plan_body("bad"), "modules": ["tenancy"]})
    assert bad.status_code == 400

    addon = billing.post(
        f"{V1}/platform/addons/", {"code": "hostel_addon", "name": "Hostel", "module": "hostel"}
    )
    assert addon.status_code == 201, addon.content
    assert billing.get(f"{V1}/platform/addons/").json()[0]["module"] == "hostel"


def test_prices_are_entered_replaced_and_deactivated_never_edited():
    billing = _staff("billing@example.com", "platform_billing")
    billing.post(f"{V1}/platform/plans/", _plan_body())
    body = {"plan": "starter", "currency": "BDT", "interval": "month", "amount": "1500.00"}
    first = billing.post(f"{V1}/platform/prices/", body)
    assert first.status_code == 201, first.content
    second = billing.post(f"{V1}/platform/prices/", {**body, "amount": "1750.50"})
    rows = billing.get(f"{V1}/platform/prices/?plan=starter").json()
    assert [(r["amount"], r["active"]) for r in rows] == [("1750.50", True), ("1500.00", False)]
    assert billing.post(f"{V1}/platform/prices/", {**body, "amount": "-1"}).status_code == 400
    both = {**body, "addon": "x"}
    assert billing.post(f"{V1}/platform/prices/", both).status_code == 400
    price_id = second.json()["id"]
    done = billing.post(f"{V1}/platform/prices/{price_id}/deactivate/")
    assert (done.status_code, done.json()["active"]) == (200, False)
    assert not Price.objects.filter(active=True).exists()
    # Without a fresh step-up, price changes are refused (permission flag).
    stale = _staff("billing2@example.com", "platform_billing", step_up=False)
    assert stale.post(f"{V1}/platform/prices/", body).json()["code"] == "step_up_required"


def test_feature_flags_and_module_catalogue():
    admin = _staff("sa@example.com", "super_admin")
    support = _staff("support@example.com", "platform_support")
    modules = admin.get(f"{V1}/platform/modules/").json()
    by_code = {m["code"]: m for m in modules}
    assert by_code["tenancy"]["category"] == "platform" and by_code["tenancy"]["available"]
    assert by_code["academics"]["available"] is True  # built in Phase 6
    assert by_code["students"]["available"] is False
    body = {"key": "new.dashboard", "default_enabled": False, "rules": {"percentage": 10}}
    saved = admin.post(f"{V1}/platform/feature-flags/", body)
    assert saved.status_code == 200, saved.content
    assert admin.get(f"{V1}/platform/feature-flags/").json()[0]["key"] == "new.dashboard"
    assert support.post(f"{V1}/platform/feature-flags/", body).status_code == 403
    invalid = admin.post(f"{V1}/platform/feature-flags/", {**body, "key": "Bad Key"})
    assert invalid.status_code == 400


def test_subscription_management_for_one_tenant(admin, tenant_factory):
    tenant = tenant_factory(slug="alpha")
    services.create_plan(actor=admin.user, code="starter", name="Starter", modules=["fees"])
    services.create_addon(actor=admin.user, code="hostel_addon", name="Hostel", module="hostel")
    billing = _staff("billing@example.com", "platform_billing")
    base = f"{V1}/platform/tenants/{tenant.id}/subscription/"

    empty = billing.get(base).json()
    assert (empty["plan"], empty["status"]) == (None, None)
    assert {m["code"] for m in empty["modules"] if m["enabled"]} >= {"tenancy", "identity"}
    short = billing.post(f"{base}plan/", {"plan": "starter", "reason": "short"})
    assert short.status_code == 400
    trial = billing.post(f"{base}trial/", {"plan": "starter", "days": 7, "reason": REASON})
    assert trial.status_code == 200, trial.content
    assert trial.json()["status"] == "trialing"
    assigned = billing.post(f"{base}plan/", {"plan": "starter", "reason": REASON}).json()
    assert (assigned["plan"]["code"], assigned["status"]) == ("starter", "active")
    fees = next(m for m in assigned["modules"] if m["code"] == "fees")
    assert (fees["source"], fees["enabled"], fees["reason"]) == ("plan", False, "not_built")

    added = billing.post(f"{base}addons/", {"addon": "hostel_addon", "reason": REASON})
    assert [a["code"] for a in added.json()["addons"]] == ["hostel_addon"]
    removed = billing.post(f"{base}addons/hostel_addon/remove/", {"reason": REASON})
    assert removed.json()["addons"] == []
    gone = billing.post(f"{base}addons/hostel_addon/remove/", {"reason": REASON})
    assert gone.status_code == 404

    granted = billing.post(
        f"{base}overrides/", {"module": "staff", "kind": "grant", "reason": REASON}
    ).json()
    assert [(o["module"], o["kind"]) for o in granted["overrides"]] == [("staff", "grant")]
    ended = billing.post(f"{base}overrides/staff/end/", {"reason": REASON})
    assert ended.json()["overrides"] == []
    assert billing.post(f"{base}overrides/staff/end/", {"reason": REASON}).status_code == 404

    assert billing.get(f"{V1}/platform/tenants/{uuid.uuid4()}/subscription/").status_code == 404
    support = _staff("support@example.com", "platform_support")
    assert support.get(base).status_code == 403
    assert support.post(f"{base}plan/", {"plan": "starter", "reason": REASON}).status_code == 403
    stale = _staff("billing2@example.com", "platform_billing", step_up=False)
    refused = stale.post(f"{base}plan/", {"plan": "starter", "reason": REASON})
    assert refused.json()["code"] == "step_up_required"


def _member(org, email: str, template: str) -> Api:
    person = make_user(email, mfa=template != "teacher")
    grant_role(org.tenant, person.user, template)
    api = Api(host=tenant_host(org.tenant))
    api.login(person, expect="authenticated")
    return api


def test_the_tenant_sees_its_own_subscription_and_entitlements(admin, org):
    services.create_plan(
        actor=admin.user,
        code="starter",
        name="Starter",
        modules=["fees"],
        limits={"max_institutions": 3, "max_campuses": 6},
    )
    services.assign_plan(
        actor=admin.user, tenant_id=org.tenant.id, plan_code="starter", reason=REASON
    )
    owner = _member(org, "boss@example.com", "tenant_owner")
    page = owner.get(f"{V1}/tenant/subscription/")
    assert page.status_code == 200, page.content
    body = page.json()
    assert (body["plan"]["code"], body["status"]) == ("starter", "active")
    assert body["limits"] == {
        "max_institutions": {"limit": 3, "used": 2},
        "max_campuses": {"limit": 6, "used": 3},
    }
    assert next(m for m in body["modules"] if m["code"] == "fees")["reason"] == "not_built"
    teacher = _member(org, "plain@example.com", "teacher")
    assert teacher.get(f"{V1}/tenant/subscription/").status_code == 403
    context = owner.get(f"{V1}/me/context/").json()["entitlements"]
    assert "tenancy" in context["modules"] and "fees" not in context["modules"]
    assert context["limits"]["max_campuses"] == {"limit": 6, "used": 3}
    assert context["flags"] == {}
    # The tenant page is tenant-host only.
    assert Api().get(f"{V1}/tenant/subscription/").status_code == 404
