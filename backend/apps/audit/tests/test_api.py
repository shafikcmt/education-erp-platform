"""Audit log API (plan §6.8/§6.9): masked IPs, filters, step-up reveal, blind-index search."""

import pytest

from apps.audit.models import AuditEvent
from apps.audit.services import record
from tests.helpers import Api, make_user

pytestmark = pytest.mark.django_db


def _event(ip="203.0.113.9"):
    from django.test import RequestFactory

    return record("identity.logout", request=RequestFactory().get("/", REMOTE_ADDR=ip))


def test_list_masks_ips_and_filters(admin_api):
    event = _event()
    body = admin_api.get("/api/v1/platform/audit-events/", action="identity.logout").json()
    rows = body["results"]
    assert [r["id"] for r in rows] == [str(event.pk)]
    assert rows[0]["ip_masked"] == "203.0.113.•"
    assert "203.0.113.9" not in repr(body)
    assert admin_api.get("/api/v1/platform/audit-events/", occurred_after="bad").status_code == 400


def test_tenant_events_are_not_listed_on_the_platform(admin_api, tenant_factory):
    """D3: a tenant's events exist only inside that tenant (private dual-scope RLS, M6); the
    platform can neither list them nor write into a tenant's log from outside it."""
    from django.db import transaction
    from django.db.utils import ProgrammingError

    from apps.core.tenancy import tenant_atomic

    tenant = tenant_factory()
    with tenant_atomic(tenant):
        tenant_event = record("identity.logout")
    assert tenant_event.tenant_id == tenant.id
    rows = admin_api.get("/api/v1/platform/audit-events/", action="identity.logout").json()
    assert rows["results"] == []
    assert not AuditEvent.objects.filter(pk=tenant_event.pk).exists()
    with pytest.raises(ProgrammingError, match="row-level security"), transaction.atomic():
        record("identity.logout", tenant_id=tenant.id)


def test_reveal_needs_step_up_and_is_audited(admin, admin_api):
    event = _event()
    response = admin_api.post(f"/api/v1/platform/audit-events/{event.pk}/reveal-ip/")
    assert response.json() == {"ip": "203.0.113.9"}
    assert AuditEvent.objects.filter(
        action="audit.ip.revealed", actor_user_id=admin.user.pk
    ).exists()
    viewer = make_user("viewer@example.com", roles=("platform_support",), mfa=True)
    api = Api()
    api.login(viewer)
    assert api.post(f"/api/v1/platform/audit-events/{event.pk}/reveal-ip/").status_code == 403


def test_reveal_without_fresh_step_up_is_refused():
    sa = make_user("sa@example.com", roles=("super_admin",), mfa=True)
    api = Api()
    api.login(sa)
    event = _event()
    response = api.post(f"/api/v1/platform/audit-events/{event.pk}/reveal-ip/")
    assert response.json()["code"] == "step_up_required"


def test_ip_search_uses_the_blind_index_and_needs_view_ip(admin_api):
    hit, _miss = _event("203.0.113.9"), _event("198.51.100.1")
    rows = admin_api.get("/api/v1/platform/audit-events/", ip="203.0.113.9").json()["results"]
    assert [r["id"] for r in rows] == [str(hit.pk)]
    support = make_user("s@example.com", roles=("platform_support",), mfa=True)
    api = Api()
    api.login(support)
    assert api.get("/api/v1/platform/audit-events/", ip="203.0.113.9").status_code == 400
