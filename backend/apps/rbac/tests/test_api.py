"""Roles and platform-role assignment API (plan §5.1 guard rails, §8)."""

import pytest

from apps.audit.models import AuditEvent
from apps.rbac.models import PlatformRoleAssignment, Role
from tests.helpers import Api, make_user

pytestmark = pytest.mark.django_db


def _role_id(code):
    return str(Role.objects.get(code=code, tenant_id__isnull=True).pk)


def test_role_crud_with_audit(admin_api):
    created = admin_api.post(
        "/api/v1/platform/roles/",
        {
            "code": "auditor",
            "name": "Auditor",
            "name_i18n": {"bn": "নিরীক্ষক"},
            "permissions": ["audit.event.view", "identity.user.view"],
        },
    )
    assert created.status_code == 201, created.content
    role_id = created.json()["id"]
    assert created.json()["permissions"] == ["audit.event.view", "identity.user.view"]
    patched = admin_api.patch(
        f"/api/v1/platform/roles/{role_id}/",
        {"name": "Auditor 2", "permissions": ["audit.event.view"]},
    )
    assert patched.json()["permissions"] == ["audit.event.view"]
    changed = AuditEvent.objects.get(action="rbac.role.permissions_changed")
    assert changed.metadata == {
        "role_code": "auditor",
        "added": [],
        "removed": ["identity.user.view"],
    }
    duplicate = admin_api.post(
        "/api/v1/platform/roles/", {"code": "auditor", "name": "x", "permissions": []}
    )
    assert duplicate.status_code == 400
    unknown = admin_api.post(
        "/api/v1/platform/roles/", {"code": "other", "name": "x", "permissions": ["nope.nope.nope"]}
    )
    assert unknown.status_code == 400
    assert admin_api.delete(f"/api/v1/platform/roles/{role_id}/").status_code == 204
    assert {"rbac.role.created", "rbac.role.updated", "rbac.role.deleted"} <= set(
        AuditEvent.objects.values_list("action", flat=True)
    )


def test_system_roles_are_read_only_via_api(admin_api):
    response = admin_api.patch(f"/api/v1/platform/roles/{_role_id('super_admin')}/", {"name": "x"})
    assert response.status_code == 409 and response.json()["code"] == "system_role_read_only"
    assert (
        admin_api.delete(f"/api/v1/platform/roles/{_role_id('platform_support')}/").status_code
        == 409
    )


def test_grant_and_revoke_platform_roles(admin_api):
    target = make_user("t@example.com")
    path = f"/api/v1/platform/users/{target.user.pk}/platform-roles/"
    granted = admin_api.post(path, {"role": _role_id("platform_support"), "reason": "on-call"})
    assert granted.status_code == 201
    assert admin_api.get(path).json()[0]["role_code"] == "platform_support"
    template = admin_api.post(path, {"role": _role_id("teacher"), "reason": "not allowed"})
    assert template.status_code == 404  # templates are not platform roles
    assert admin_api.delete(f"{path}{granted.json()['id']}/").status_code == 204
    assert not PlatformRoleAssignment.objects.filter(user=target.user).exists()
    actions = list(
        AuditEvent.objects.filter(action__startswith="rbac.platform_role").values_list(
            "action", "metadata"
        )
    )
    assert ("rbac.platform_role.granted", {"role_code": "platform_support"}) in actions
    assert ("rbac.platform_role.revoked", {"role_code": "platform_support"}) in actions


def test_last_super_admin_cannot_be_revoked_via_api(admin, admin_api):
    assignment = PlatformRoleAssignment.objects.get(user=admin.user, role__code="super_admin")
    path = f"/api/v1/platform/users/{admin.user.pk}/platform-roles/{assignment.pk}/"
    response = admin_api.delete(path)
    assert response.status_code == 409 and response.json()["code"] == "last_super_admin"


def test_non_super_admin_cannot_grant_super_admin():
    manager = make_user("m@example.com", mfa=True)
    role = Role.objects.create(code="granter", name="Granter", kind="platform")
    from apps.rbac.models import Permission, RolePermission

    for code in ("rbac.platform_role.assign", "identity.user.view"):
        RolePermission.objects.create(role=role, permission=Permission.objects.get(code=code))
    PlatformRoleAssignment.objects.create(user=manager.user, role=role, granted_at=role.created_at)
    api = Api()
    api.login(manager)
    api.step_up(manager)
    target = make_user("t@example.com")
    response = api.post(
        f"/api/v1/platform/users/{target.user.pk}/platform-roles/",
        {"role": _role_id("super_admin"), "reason": "escalation attempt"},
    )
    assert response.status_code == 403 and response.json()["code"] == "privilege_escalation"


def test_permission_catalog_lists_flags(admin_api):
    rows = {r["code"]: r for r in admin_api.get("/api/v1/platform/permissions/").json()}
    assert rows["audit.event.view_ip"]["requires_step_up"] is True
    assert rows["identity.account.view_own"]["requires_mfa"] is False
