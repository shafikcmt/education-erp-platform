"""Module entitlement enforcement on tenant views and tenant tasks (Phase 4 M4; ADR-052,
ADR-054 Q3). Through the real middleware stack on a tenant host, with the probe view
``/_probe/module/`` (module ``academics``, permission ``tenancy.member.view``)."""

from __future__ import annotations

import pytest

from apps.module_registry import services as registry_services
from apps.module_registry.permissions import ModuleEntitled
from apps.tenancy.tasking import TenantTaskRefused
from tests.helpers import Api, make_user
from tests.isolation.factories import grant_role, tenant_events, tenant_host
from tests.isolation_app.tasks import academics_only

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])
PROBE = "/_probe/module/"
REASON = "Pilot agreement for the academics module"


def _api(org, email: str, template: str) -> Api:
    person = make_user(email, mfa=template != "teacher")
    grant_role(org.tenant, person.user, template)
    api = Api(host=tenant_host(org.tenant))
    api.login(person, expect="authenticated")
    return api


def _grant(admin, org, code: str = "academics") -> None:
    registry_services.set_override(
        actor=admin.user, tenant_id=org.tenant.id, module_code=code, kind="grant", reason=REASON
    )


def test_a_module_the_tenant_lacks_is_refused_before_the_permission(org):
    api = _api(org, "deputy@example.com", "institution_admin")
    response = api.get(PROBE)
    assert (response.status_code, response.json()["code"]) == (403, "module_not_entitled")
    # A permission-less member gets the same answer: the entitlement is checked first.
    teacher = _api(org, "plain@example.com", "teacher")
    assert teacher.get(PROBE).json()["code"] == "module_not_entitled"
    denials = [
        e
        for e in tenant_events(org.tenant, using="audit_durable", action="authz.denied")
        if e.metadata.get("reason") == "module_not_entitled"
    ]
    assert [e.metadata["module"] for e in denials] == ["academics", "academics"]


def test_anonymous_callers_get_401_without_learning_entitlements(org):
    response = Api(host=tenant_host(org.tenant)).get(PROBE)
    assert response.status_code in (401, 403)
    assert response.json()["code"] != "module_not_entitled"


def test_an_entitled_module_still_needs_the_permission(admin, org, built):
    _grant(admin, org)
    assert _api(org, "deputy@example.com", "institution_admin").get(PROBE).status_code == 200
    denied = _api(org, "plain@example.com", "teacher").get(PROBE)
    assert (denied.status_code, denied.json()["code"]) == (403, "permission_denied")


def test_revoking_the_module_takes_effect_on_the_next_request(admin, org, built):
    _grant(admin, org)
    api = _api(org, "deputy@example.com", "institution_admin")
    assert api.get(PROBE).status_code == 200  # fills the entitlement cache
    registry_services.set_override(
        actor=admin.user,
        tenant_id=org.tenant.id,
        module_code="academics",
        kind="revoke",
        reason=REASON,
    )
    assert api.get(PROBE).json()["code"] == "module_not_entitled"


def test_unbuilt_modules_stay_refused_even_when_granted(admin, org):
    from apps.core.tenancy import tenant_atomic
    from apps.module_registry import entitlements
    from apps.module_registry.errors import ModuleNotEntitledError

    _grant(admin, org, "fees")  # no ``built`` patch: fees is not built yet
    with tenant_atomic(org.tenant):
        assert not entitlements.is_entitled("fees")
        with pytest.raises(ModuleNotEntitledError):
            entitlements.require_module("fees")


def test_tenant_tasks_of_a_module_are_refused_for_tenants_without_it(admin, org, built):
    with pytest.raises(TenantTaskRefused, match="not entitled"):
        academics_only.apply(kwargs={"tenant_id": str(org.tenant.id)}).get()
    _grant(admin, org)
    result = academics_only.apply(kwargs={"tenant_id": str(org.tenant.id)}).get()
    assert result == str(org.tenant.id)


def test_module_codes_are_validated_when_declared():
    with pytest.raises(ValueError, match="Unknown module"):
        ModuleEntitled("no_such_module")
    assert ModuleEntitled("academics").module_code == "academics"
