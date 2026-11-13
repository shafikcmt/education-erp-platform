"""Tenant request path (Phase 3 M3): host decision table through the real middleware stack,
resolution, tenant transaction, rollback (R1, R5-R8), leaks (L2-L4, L7, L8), host classes,
membership gate and session-host binding. Runs as ``erp_app``.

Tenant hosts are off by default; the ``tenant_hosts`` / ``tenant_site`` fixtures switch them
on and add the probe endpoints of ``tests.isolation_app``.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from apps.audit.models import AuditEvent
from apps.core.tenancy import current_tenant, tenant_atomic
from apps.core.tenancy.transaction import connections_with_tenant_state
from apps.identity.models import SessionRecord
from apps.tenancy.rules import TenantStatus
from tests.helpers import Api, make_user
from tests.isolation.factories import add_member, tenant_host
from tests.isolation_app import views as probe
from tests.isolation_app.models import ProbeRecord

# The durable audit alias is a second connection; pytest-django wraps it in its own test
# transaction, so durable events are read back through that alias and vanish after the test.
DURABLE = "audit_durable"
pytestmark = pytest.mark.django_db(databases=["default", DURABLE, "isolation_secondary"])

NOT_FOUND_KEYS = {"type", "title", "status", "code", "detail", "request_id"}


def _get(host: str, path: str = "/_probe/whoami/", **extra: Any) -> Any:
    return Client(HTTP_HOST=host).get(path, **extra)


def _uniform(response: Any) -> dict[str, Any]:
    """The response is the uniform 404; returns its body without the per-request id."""
    assert response.status_code == 404
    assert response["Content-Type"] == "application/problem+json"
    body: dict[str, Any] = response.json()
    assert set(body) == NOT_FOUND_KEYS and body["code"] == "not_found"
    body.pop("request_id")
    return body


def _names(tenant) -> set[str]:
    with tenant_atomic(tenant):
        return set(ProbeRecord.objects.values_list("name", flat=True))


def _events(tenant, action: str) -> list[AuditEvent]:
    return list(AuditEvent.objects.using(DURABLE).filter(tenant_id=tenant.id, action=action))


# --------------------------------------------------------------------------- decision table
def test_disabled_mode_serves_only_platform_hosts_and_looks_nothing_up(tenant_factory, settings):
    """Step 3 (D1): the default. An existing tenant's host is indistinguishable from any other
    and no query at all is issued for it."""
    assert settings.TENANT_HOSTS_ENABLED is False
    tenant = tenant_factory(slug="acme")
    bodies = []
    with CaptureQueriesContext(connection) as queries:
        for host in (tenant_host(tenant), "nobody.tenants.test", "tenants.test"):
            bodies.append(_uniform(_get(host, "/api/v1/me/")))
            bodies.append(_uniform(_get(host, "/api/v1/auth/csrf/")))
    assert len(queries) == 0
    assert all(body == bodies[0] for body in bodies)
    assert _get("testserver", "/api/v1/auth/csrf/").status_code == 200


def test_health_probes_ignore_the_host_policy(settings):
    for host in ("testserver", "anything.tenants.test"):
        response = _get(host, "/healthz")
        assert response.status_code == 200
        assert "sessionid" not in response.cookies


def test_disallowed_host_is_still_a_400(settings):
    assert _get("evil.example.net", "/api/v1/auth/csrf/").status_code == 400


def test_unknown_provisioning_deleted_and_unverified_hosts_are_indistinguishable(
    tenant_site, tenant_factory
):
    """Steps 4-5: one body for every host that is not a usable tenant."""
    from tests.isolation.factories import make_tenant_site

    make_tenant_site(slug="newbie", status=TenantStatus.PROVISIONING)
    make_tenant_site(slug="gone", status=TenantStatus.DELETED)
    make_tenant_site(slug="pending", verified=False)
    tenant_factory(slug="nodomain")
    hosts = [
        "newbie.tenants.test",
        "gone.tenants.test",
        "pending.tenants.test",
        "nodomain.tenants.test",
        "never-existed.tenants.test",
        "a.b.tenants.test",
        "www.tenants.test",
        "tenants.test",
    ]
    bodies = [_uniform(_get(host)) for host in hosts]
    assert all(body == bodies[0] for body in bodies)
    # Same body as an unknown path on the platform host.
    assert _uniform(_get("testserver", "/api/v1/does-not-exist/")) == bodies[0]


def test_step_5_costs_exactly_one_lookup_for_every_candidate(tenant_site):
    tenant_site(slug="acme")
    for host in ("acme.tenants.test", "never-existed.tenants.test"):
        with CaptureQueriesContext(connection) as queries:
            _get(host, "/api/v1/does-not-exist/")
        lookups = [q for q in queries if "tenancy_resolve_host" in q["sql"]]
        assert len(lookups) == 1, host


@pytest.mark.parametrize("status", ["active", "suspended", "offboarding"])
def test_resolvable_statuses_get_a_tenant_context(tenant_site, status):
    tenant = tenant_site(slug="acme", status=status)
    body = _get("ACME.tenants.test:8443").json()
    assert body["host_kind"] == "tenant"
    assert body["tenant"] == body["context"] == body["setting"] == str(tenant.id)
    assert body["status"] == status
    assert body["scope"] == f"t:{tenant.id}:-:-"
    assert body["lock_timeout"] == "5s"


def test_platform_host_has_no_tenant_and_no_transaction(tenant_site):
    tenant_site(slug="acme")
    body = _get("testserver").json()
    assert (body["host_kind"], body["tenant"], body["context"], body["setting"]) == (
        "platform",
        None,
        None,
        "",
    )
    assert body["scope"] == "platform"
    assert body["lock_timeout"] != "5s"


def test_tenant_is_chosen_from_the_host_only(tenant_site):
    """Headers, query strings and bodies naming another tenant change nothing."""
    a, b = tenant_site(slug="acme"), tenant_site(slug="bravo")
    with tenant_atomic(b):
        ProbeRecord.objects.create(name="b-secret")
    response = Client(HTTP_HOST=tenant_host(a)).get(
        "/_probe/records/",
        {"tenant": str(b.id), "tenant_id": str(b.id)},
        HTTP_X_TENANT=str(b.id),
        HTTP_X_TENANT_ID=b.slug,
        HTTP_X_ORIGINAL_HOST=tenant_host(b),
        HTTP_FORWARDED=f"host={tenant_host(b)}",
    )
    body = response.json()
    assert body["names"] == [] and body["setting"] == str(a.id)
    assert body["raw"] == []  # raw SQL under RLS sees only tenant A (which has no rows)


def test_forwarded_host_is_a_proxy_header_and_gets_the_full_policy(tenant_site, settings):
    """``X-Forwarded-Host`` is trusted because Nginx overwrites it on every request (like
    ``X-Real-IP``): the Next.js server relays the browser's host through it. It is therefore
    THE request host, and it passes ALLOWED_HOSTS and the whole host policy like ``Host``."""
    from pathlib import Path

    assert settings.USE_X_FORWARDED_HOST is True
    nginx = (Path(settings.BASE_DIR).parent / "infra/nginx/nginx.conf").read_text()
    assert "proxy_set_header Host $host;" in nginx
    assert "proxy_set_header X-Forwarded-Host $host;" in nginx  # client value never survives
    tenant = tenant_site(slug="acme")
    via_proxy = Client(HTTP_HOST="api").get(
        "/_probe/whoami/", HTTP_X_FORWARDED_HOST=tenant_host(tenant)
    )
    assert via_proxy.json()["tenant"] == str(tenant.id)
    for forwarded, status in (("nobody.tenants.test", 404), ("evil.example.net", 400)):
        response = Client(HTTP_HOST="testserver").get(
            "/_probe/whoami/", HTTP_X_FORWARDED_HOST=forwarded
        )
        assert response.status_code == status, forwarded


# --------------------------------------------------------------------------- host classes
def test_views_are_platform_only_unless_they_opt_in(tenant_site):
    tenant = tenant_site(slug="acme")
    host = tenant_host(tenant)
    reference = _uniform(_get(host, "/api/v1/does-not-exist/"))
    for path in (
        "/_probe/platform-only/",
        "/api/v1/platform/users/",
        "/api/v1/auth/password/reset/",
        "/api/v1/audit/events/",
        "/api/v1/system/health/",
        "/api/v1/me/sessions/",
    ):
        assert _uniform(_get(host, path)) == reference, path
    assert _get(host, "/_probe/tenant-only/").status_code == 200
    assert _uniform(_get("testserver", "/_probe/tenant-only/")) == reference
    assert _get("testserver", "/_probe/platform-only/").status_code == 200
    for path in ("/api/v1/auth/csrf/",):
        assert _get(host, path).status_code == 200
    assert _get(host, "/api/v1/me/").status_code == 401


# --------------------------------------------------------------------------- rollback
def _post(tenant, name: str, then: str = "") -> Any:
    suffix = f"?then={then}" if then else ""
    return Client(HTTP_HOST=tenant_host(tenant), raise_request_exception=False).post(
        f"/_probe/records/{suffix}", json.dumps({"name": name}), content_type="application/json"
    )


def test_success_commits_and_runs_on_commit(tenant_site, django_capture_on_commit_callbacks):
    tenant = tenant_site(slug="acme")
    probe.ON_COMMIT_LOG.clear()
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        assert _post(tenant, "kept").status_code == 201
    assert len(callbacks) == 1 and probe.ON_COMMIT_LOG == ["kept"]
    assert _names(tenant) == {"kept"}


@pytest.mark.parametrize(("then", "status"), [("403", 403), ("raise", 500), ("stream", 500)])
def test_error_responses_roll_the_request_back(
    tenant_site, django_capture_on_commit_callbacks, then, status
):
    """R1 (data part), R5, R8 and L7: a 4xx, an unhandled exception and a refused streaming
    body all leave no row behind, and their ``on_commit`` side effects never run."""
    tenant = tenant_site(slug="acme")
    probe.ON_COMMIT_LOG.clear()
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = _post(tenant, "lost", then)
    assert response.status_code == status
    assert response["Content-Type"] == "application/problem+json"
    assert callbacks == [] and probe.ON_COMMIT_LOG == []
    assert _names(tenant) == set()
    # R8 / L2: nothing leaks, and the same connection serves the next request.
    assert current_tenant() is None and connections_with_tenant_state() == []
    assert _post(tenant, "next").status_code == 201
    assert _names(tenant) == {"next"}


def test_service_savepoint_rolls_back_partially_while_the_request_commits(tenant_site):
    """R6."""
    tenant = tenant_site(slug="acme")
    assert _post(tenant, "outer", "savepoint").status_code == 201
    assert _names(tenant) == {"outer"}


def test_platform_host_errors_do_not_roll_anything_back(tenant_site):
    """R7: the rollback rule exists only inside a tenant transaction."""
    make_user("someone@example.com")
    before = AuditEvent.objects.filter(action="identity.login.failed").count()
    response = Api().post(
        "/api/v1/auth/login/", {"email": "someone@example.com", "password": "wrong"}
    )
    assert response.status_code == 401
    assert AuditEvent.objects.filter(action="identity.login.failed").count() == before + 1
    assert not connection.needs_rollback


def test_platform_request_after_a_tenant_request_sees_no_tenant_rows(tenant_site):
    """L3: same thread, same connection."""
    tenant = tenant_site(slug="acme")
    assert _post(tenant, "row").status_code == 201
    first = _get(tenant_host(tenant)).json()
    second = _get("testserver").json()
    assert first["pid"] == second["pid"]
    assert first["raw"] == [str(tenant.id)]
    assert (second["raw"], second["setting"], second["context"]) == ([], "", None)


def test_blocked_isolation_violation_is_audited_in_the_platform_log(tenant_site):
    """P14: the query guard stops a query that would run outside the tenant transaction; the
    request fails and rolls back, and the platform log records it with the tenant id as
    metadata only."""
    tenant = tenant_site(slug="acme")
    response = _post(tenant, "never", "bypass")
    assert response.status_code == 500 and response.json()["code"] == "internal_error"
    assert "TenantContext" not in response.content.decode()  # no internals in the body
    assert _names(tenant) == set()
    events = AuditEvent.objects.filter(action="tenancy.isolation.blocked")
    assert [(e.tenant_id, e.outcome, e.metadata) for e in events] == [
        (
            None,
            "denied",
            {
                "reason": "TenantContextNotApplied",
                "tenant_id": str(tenant.id),
                "host_kind": "tenant",
            },
        )
    ]
    assert current_tenant() is None and connections_with_tenant_state() == []


def test_tenant_requests_log_their_transaction_time_and_warn_when_slow(tenant_site, settings):
    import structlog

    tenant = tenant_site(slug="acme")
    with structlog.testing.capture_logs() as logs:
        _get(tenant_host(tenant))
        settings.TENANT_TX_WARN_MS = -1  # everything is "slow"
        _get(tenant_host(tenant))
        _get("testserver")
    entries = [entry for entry in logs if entry["event"] == "tenant_request"]
    assert [(e["log_level"], e["slow"], e["status"]) for e in entries] == [
        ("info", False, 200),
        ("warning", True, 200),
    ]
    assert all(e["tenant_id"] == str(tenant.id) and e["tx_ms"] >= 0 for e in entries)


def test_rejected_hosts_are_logged_sampled_and_never_stored(tenant_site):
    import structlog

    from apps.tenancy import middleware

    before = AuditEvent.objects.count()
    with structlog.testing.capture_logs() as logs:
        for _ in range(2 * middleware._REJECTION_LOG_SAMPLE):
            _get("nobody.tenants.test")
    rejected = [entry for entry in logs if entry["event"] == "tenancy.host.rejected"]
    assert len(rejected) == 2 and rejected[0]["reason"] == "unknown_tenant"
    assert AuditEvent.objects.count() == before


# --------------------------------------------------------------------------- gate (Q5)
def _member_api(tenant, email: str = "member@example.com", status: str = "active"):
    person = make_user(email)
    membership = add_member(tenant, person.user, status="active")
    api = Api(host=tenant_host(tenant))
    api.login(person, expect="authenticated")
    if status != "active":
        with tenant_atomic(tenant):
            type(membership).objects.filter(pk=membership.pk).update(status=status)
    return api, person, membership


def _set_tenant_status(tenant, *statuses: str) -> None:
    from apps.tenancy.models import Tenant

    row = Tenant.objects.get(pk=tenant.id)
    for status in statuses:
        row.status = status
        row.save()


def test_active_member_passes_the_gate_and_reads_only_own_account(tenant_site):
    tenant = tenant_site(slug="acme")
    api, person, _ = _member_api(tenant)
    me = api.get("/api/v1/me/")
    assert me.status_code == 200 and me.json()["email"] == person.user.email
    record = SessionRecord.objects.get(user=person.user)
    assert record.host == "acme.tenants.test"


def test_membership_changes_take_effect_on_the_next_request(tenant_site):
    tenant = tenant_site(slug="acme")
    api, _person, membership = _member_api(tenant)
    assert api.get("/api/v1/me/").status_code == 200
    with tenant_atomic(tenant):
        type(membership).objects.filter(pk=membership.pk).update(status="suspended")
    denied = api.get("/api/v1/me/")
    assert (denied.status_code, denied.json()["code"]) == (403, "membership_inactive")
    with tenant_atomic(tenant):
        type(membership).objects.filter(pk=membership.pk).delete()
    denied = api.get("/api/v1/me/")
    assert (denied.status_code, denied.json()["code"]) == (403, "not_a_member")
    reasons = {e.metadata["reason"] for e in _events(tenant, "authz.denied")}
    assert reasons == {"membership_inactive", "not_a_member"}
    # Signing out stays possible (it only ends the caller's own session).
    assert api.post("/api/v1/auth/logout/").status_code == 204


def test_suspended_tenant_denies_everyone_including_members(tenant_site):
    """Q5 / D2: fail closed until the restricted owner mode exists (M5)."""
    tenant = tenant_site(slug="acme")
    api, _, _ = _member_api(tenant)
    _set_tenant_status(tenant, TenantStatus.SUSPENDED)
    for method, path in (("get", "/api/v1/me/"), ("patch", "/api/v1/me/")):
        response = getattr(api, method)(path)
        assert (response.status_code, response.json()["code"]) == (403, "tenant_suspended"), path
    assert api.get("/_probe/protected/").json()["code"] == "tenant_suspended"
    _set_tenant_status(tenant, TenantStatus.ACTIVE)
    assert api.get("/api/v1/me/").status_code == 200


def test_offboarding_tenant_accepts_no_writes(tenant_site):
    tenant = tenant_site(slug="acme")
    api, _, _ = _member_api(tenant)
    _set_tenant_status(tenant, TenantStatus.OFFBOARDING)
    assert api.get("/api/v1/me/").status_code == 200
    denied = api.patch("/api/v1/me/", {"full_name": "Changed"})
    assert (denied.status_code, denied.json()["code"]) == (403, "tenant_unavailable")
    assert api.post("/api/v1/auth/logout/").status_code == 204


def test_nobody_holds_platform_permissions_on_a_tenant_host(tenant_site):
    """Default deny (ADR-031/037): a Super Admin who is also a member gets nothing here.
    R1 (audit part): the denial is durable although the request rolled back."""
    tenant = tenant_site(slug="acme")
    admin = make_user("root@example.com", roles=("super_admin",), mfa=True)
    add_member(tenant, admin.user)
    api = Api(host=tenant_host(tenant))
    api.login(admin, expect="authenticated")
    assert Api().client.get("/_probe/protected/").status_code in (401, 403)
    response = api.get("/_probe/protected/")
    assert (response.status_code, response.json()["code"]) == (403, "permission_denied")
    events = _events(tenant, "authz.denied")
    assert [e.metadata for e in events] == [
        {"permission": "identity.user.view", "reason": "missing_permission"}
    ]
    assert events[0].actor_user_id == admin.user.pk


# --------------------------------------------------------------------------- session binding
def test_a_session_is_valid_only_on_its_own_host(tenant_site):
    a, b = tenant_site(slug="acme"), tenant_site(slug="bravo")
    api, person, _ = _member_api(a)
    add_member(b, person.user)
    cookie = api.client.cookies["sessionid"].value
    for host in (tenant_host(b), "testserver"):
        thief = Client(HTTP_HOST=host)
        thief.cookies["sessionid"] = cookie
        response = thief.get("/api/v1/me/")
        assert response.status_code == 401, host
        # The misplaced cookie is dropped on that host only ...
        assert response.cookies["sessionid"].value == ""
    blocked = AuditEvent.objects.filter(
        action="tenancy.isolation.blocked", actor_user_id=person.user.pk
    )
    assert {(e.tenant_id, e.metadata["reason"], e.metadata["host_kind"]) for e in blocked} == {
        (None, "session_host_mismatch", "tenant"),
        (None, "session_host_mismatch", "platform"),
    }
    # ... and the real session keeps working (replaying a cookie can't sign the user out).
    assert api.get("/api/v1/me/").status_code == 200
    assert SessionRecord.objects.get(user=person.user).revoked_at is None


def test_phase_2_session_records_with_a_port_still_match(tenant_site):
    person = make_user("legacy@example.com")
    api = Api()
    api.login(person, expect="authenticated")
    SessionRecord.objects.filter(user=person.user).update(host="TestServer:8080")
    assert api.get("/api/v1/me/").status_code == 200
