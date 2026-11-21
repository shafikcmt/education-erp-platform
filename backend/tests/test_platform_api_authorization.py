"""Allowed and denied tests for every platform endpoint (plan §8, §10 "API authz")."""

import uuid

import pytest

from apps.audit.services import record
from apps.rbac.models import PlatformRoleAssignment, Role, RoleKind
from tests.helpers import Api, make_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def target(db):
    return make_user("target@example.com")


def _endpoints(target_id, role_id, assignment_id, event_id):
    u = f"/api/v1/platform/users/{target_id}"
    return [
        ("get", "/api/v1/platform/users/", None),
        ("post", "/api/v1/platform/users/", {"email": f"n{uuid.uuid4().hex[:6]}@example.com"}),
        ("get", f"{u}/", None),
        ("patch", f"{u}/", {"display_name": "T"}),
        ("post", f"{u}/deactivate/", None),
        ("post", f"{u}/reactivate/", None),
        ("post", f"{u}/sessions/revoke/", None),
        ("post", f"{u}/mfa/reset/", {"reason": "ticket 123"}),
        ("post", f"{u}/activation/resend/", None),
        ("get", f"{u}/platform-roles/", None),
        ("post", f"{u}/platform-roles/", {"role": str(role_id), "reason": "testing grants"}),
        ("delete", f"{u}/platform-roles/{assignment_id}/", None),
        ("get", "/api/v1/platform/permissions/", None),
        ("get", "/api/v1/platform/roles/", None),
        (
            "post",
            "/api/v1/platform/roles/",
            {
                "code": f"r_{uuid.uuid4().hex[:6]}",
                "name": "R",
                "permissions": ["identity.user.view"],
            },
        ),
        ("get", f"/api/v1/platform/roles/{role_id}/", None),
        ("get", "/api/v1/platform/audit-events/", None),
        ("post", f"/api/v1/platform/audit-events/{event_id}/reveal-ip/", None),
    ]


def _fixtures(target):
    # A platform role without permissions (platform_billing holds billing codes since Phase 4,
    # so the H2 rule would rightly stop platform support from acting on its holders).
    role, _ = Role.objects.get_or_create(
        code="audit_test_empty",
        tenant_id=None,
        defaults={"name": "Empty test role", "kind": RoleKind.PLATFORM, "is_system": False},
    )
    assignment = PlatformRoleAssignment.objects.create(
        user=target.user, role=role, granted_at=role.created_at
    )
    event = record("identity.logout", actor_user_id=target.user.pk)
    return role.pk, assignment.pk, event.pk


def test_anonymous_is_401_everywhere(target):
    api = Api()
    for method, path, body in _endpoints(target.user.pk, *_fixtures(target)):
        response = api.get(path) if method == "get" else api.send(method, path, body)
        assert response.status_code == 401, (method, path, response.status_code)


def test_ordinary_user_is_403_everywhere(target):
    api = Api()
    api.login(make_user("plain@example.com"))
    for method, path, body in _endpoints(target.user.pk, *_fixtures(target)):
        response = api.get(path) if method == "get" else api.send(method, path, body)
        assert response.status_code == 403, (method, path, response.status_code)
        assert response.json()["code"] == "permission_denied"


def test_support_role_gets_exactly_its_permissions(target):
    support = make_user("support@example.com", roles=("platform_support",), mfa=True)
    api = Api()
    api.login(support)
    api.step_up(support)
    allowed = {
        ("get", "/api/v1/platform/users/"),
        ("get", f"/api/v1/platform/users/{target.user.pk}/"),
        ("post", f"/api/v1/platform/users/{target.user.pk}/sessions/revoke/"),
        ("post", f"/api/v1/platform/users/{target.user.pk}/mfa/reset/"),
        ("get", f"/api/v1/platform/users/{target.user.pk}/platform-roles/"),
        ("get", "/api/v1/platform/audit-events/"),
    }
    for method, path, body in _endpoints(target.user.pk, *_fixtures(target)):
        response = api.get(path) if method == "get" else api.send(method, path, body)
        if (method, path) in allowed:
            assert response.status_code not in (401, 403), (method, path, response.content)
        else:
            assert response.status_code == 403, (method, path, response.content)


def test_super_admin_is_allowed_everywhere(admin_api, target):
    for method, path, body in _endpoints(target.user.pk, *_fixtures(target)):
        response = admin_api.get(path) if method == "get" else admin_api.send(method, path, body)
        # Authorized: business rules may still answer 409 (e.g. resend for an active account).
        assert response.status_code not in (401, 403, 500), (method, path, response.content)


def test_unknown_ids_are_404_not_403(admin_api):
    for path in (
        "/api/v1/platform/users/not-a-uuid/",
        f"/api/v1/platform/users/{uuid.uuid4()}/",
        f"/api/v1/platform/roles/{uuid.uuid4()}/",
    ):
        assert admin_api.get(path).status_code == 404


def test_super_admin_without_mfa_session_is_refused():
    """A super admin whose MFA was removed (e.g. by data repair) cannot use the console."""
    sa = make_user("sa@example.com", roles=("super_admin",))
    api = Api()
    assert api.login(sa) == "mfa_enrollment_required"
    assert api.get("/api/v1/platform/audit-events/").json()["code"] == "mfa_enrollment_required"


def test_denials_are_audited_and_aggregated(target):
    from apps.audit.models import AuditEvent

    api = Api()
    person = make_user("plain@example.com")
    api.login(person)
    for _ in range(3):
        api.get("/api/v1/platform/users/")
    # Scoped to this actor: the durable-audit tests (Phase 3 M3) commit real, append-only
    # ``authz.denied`` events of their own, which stay in the test database.
    denials = AuditEvent.objects.filter(action="authz.denied", actor_user_id=person.user.pk)
    assert denials.count() == 1
