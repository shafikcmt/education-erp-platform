"""RBAC engine (plan §4.4, §5): registry, seeding, has_perm matrix, scope coverage, Phase 3
pluggability, cache invalidation, guard rails, DB triggers."""

import uuid

import pytest
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.utils import DataError, InternalError, ProgrammingError

from apps.rbac import engine
from apps.rbac.engine import (
    PLATFORM,
    ScopeGrant,
    ScopeTarget,
    UnknownPermissionError,
    effective_permissions,
    has_perm,
    require_perm,
    user_requires_mfa,
)
from apps.rbac.models import Permission, PlatformRoleAssignment, Role, RoleKind, RolePermission
from apps.rbac.registry import declared_permissions
from apps.rbac.role_templates import PLATFORM_ROLES, TEMPLATE_ROLES
from apps.rbac.seeding import catalog_drift
from apps.rbac.services import (
    GuardRailViolation,
    create_role,
    grant_platform_role,
    revoke_platform_role,
    update_role,
)
from apps.rbac.sources import SELF_SERVICE_CODES
from tests.helpers import make_user

pytestmark = pytest.mark.django_db

TENANT_A, TENANT_B = uuid.uuid4(), uuid.uuid4()
INST_1, INST_2 = uuid.uuid4(), uuid.uuid4()
CAMPUS_1A, CAMPUS_1B = uuid.uuid4(), uuid.uuid4()


def test_registry_covers_the_phase_2_catalog_and_seed_is_idempotent():
    """Idempotency of the owner-run bootstrap itself is proven on a throwaway database in
    ``tests/test_permission_catalog.py`` (O1: erp_app can no longer write the catalogue)."""
    codes = set(declared_permissions())
    # 20 (Phase 2) + 17 (M4) + 4 support-session codes (M5) + 5 registry codes (M8)
    # + 1 module catalogue code (Phase 4 M1) + 6 billing and 1 flag code (Phase 4 M2)
    assert len(codes) == 88  # Phase 6: academics 8 (M1), files 2 (M3), admissions 9 (M4, M6)
    assert {"identity.user.view", "audit.event.view_ip", "rbac.platform_role.assign"} <= codes
    assert set(Permission.objects.values_list("code", flat=True)) >= codes
    assert catalog_drift() == []


def test_all_claude_md_roles_are_seeded_with_bengali_names():
    expected = {r["code"] for r in PLATFORM_ROLES + TEMPLATE_ROLES}
    assert len(expected) == 22 and "staff_member" in expected
    roles = Role.objects.filter(tenant_id__isnull=True, is_system=True)
    assert set(roles.values_list("code", flat=True)) == expected
    assert all(role.name_i18n.get("bn") for role in roles)


def test_super_admin_holds_every_permission_and_others_their_subsets():
    sa = Role.objects.get(code="super_admin", tenant_id__isnull=True)
    assert set(sa.permissions.values_list("code", flat=True)) == set(declared_permissions())
    support = Role.objects.get(code="platform_support", tenant_id__isnull=True)
    assert set(support.permissions.values_list("code", flat=True)) == {
        "identity.user.view",
        "identity.session.revoke_any",
        "identity.mfa.reset",
        "audit.event.view",
        "tenancy.support_session.request",  # Phase 3 M5 (P6)
        "tenancy.tenant.view_any",  # Phase 3 M8: find the tenant to request access to (P8)
    }


def test_deprecated_codes_are_unknown_to_the_engine():
    """Deprecation by ``sync_permissions`` is tested as the owner in
    ``tests/test_permission_catalog.py``; here: a deprecated code is unknown at runtime."""
    deprecated = Permission.objects.filter(deprecated_at__isnull=False)
    assert not deprecated.exists()
    with pytest.raises(UnknownPermissionError):
        has_perm(make_user().user, "identity.legacy.thing")


def test_permission_matrix_platform_target():
    plain = make_user("plain@example.com").user
    support = make_user("support@example.com", roles=("platform_support",)).user
    sa = make_user("sa@example.com", roles=("super_admin",)).user
    inactive = make_user("gone@example.com", roles=("super_admin",), active=False).user
    assert has_perm(plain, "identity.account.view_own")
    assert not has_perm(plain, "identity.user.view")
    assert has_perm(support, "identity.user.view")
    assert not has_perm(support, "identity.user.create")
    assert has_perm(sa, "audit.event.view_ip")
    assert not has_perm(inactive, "identity.account.view_own")
    assert not has_perm(None, "identity.account.view_own")
    with pytest.raises(UnknownPermissionError):
        has_perm(sa, "identity.no.such")
    with pytest.raises(PermissionDenied):
        require_perm(plain, "identity.user.view")


def test_super_admin_has_no_implicit_tenant_access():
    sa = make_user("sa@example.com", roles=("super_admin",)).user
    tenant_target = ScopeTarget(tenant_id=TENANT_A)
    assert not has_perm(sa, "identity.user.view", target=tenant_target)
    assert effective_permissions(sa, tenant_target) == SELF_SERVICE_CODES


@pytest.mark.parametrize(
    ("grant", "target", "covered"),
    [
        (ScopeGrant(TENANT_A), ScopeTarget(TENANT_A), True),
        (ScopeGrant(TENANT_A), ScopeTarget(TENANT_A, INST_1, CAMPUS_1A), True),
        (ScopeGrant(TENANT_A), ScopeTarget(TENANT_B), False),
        (ScopeGrant(TENANT_A, INST_1), ScopeTarget(TENANT_A, INST_1), True),
        (ScopeGrant(TENANT_A, INST_1), ScopeTarget(TENANT_A, INST_1, CAMPUS_1B), True),
        (ScopeGrant(TENANT_A, INST_1), ScopeTarget(TENANT_A, INST_2), False),
        (ScopeGrant(TENANT_A, INST_1), ScopeTarget(TENANT_A), False),
        (ScopeGrant(TENANT_A, INST_1, CAMPUS_1A), ScopeTarget(TENANT_A, INST_1, CAMPUS_1A), True),
        (ScopeGrant(TENANT_A, INST_1, CAMPUS_1A), ScopeTarget(TENANT_A, INST_1, CAMPUS_1B), False),
        (ScopeGrant(TENANT_A, INST_1, CAMPUS_1A), ScopeTarget(TENANT_A, INST_1), False),
        (ScopeGrant(TENANT_A), PLATFORM, False),
    ],
)
def test_scope_coverage_rules(grant, target, covered):
    assert grant.covers(target) is covered


class FakeTenantSource:
    """Stands in for the Phase 3 TenantMembershipSource: one user, scoped assignments."""

    def __init__(self, user_id, assignments):
        self.user_id, self.assignments = user_id, assignments

    def grants(self, actor, target):
        if actor.pk != self.user_id:
            return frozenset()
        codes: set[str] = set()
        for scope, granted in self.assignments:
            if scope.covers(target):
                codes |= granted
        return frozenset(codes)


def test_tenant_source_plugs_in_without_engine_changes():
    """ADR-032 condition: different roles in different institutions/campuses, same user."""
    user = make_user("teacher@example.com").user
    source = FakeTenantSource(
        user.pk,
        [
            (ScopeGrant(TENANT_A, INST_1, CAMPUS_1A), frozenset({"identity.user.view"})),
            (ScopeGrant(TENANT_A, INST_2), frozenset({"identity.user.create"})),
        ],
    )
    extra = (source,)
    campus_1a = ScopeTarget(TENANT_A, INST_1, CAMPUS_1A)
    assert has_perm(user, "identity.user.view", target=campus_1a, extra_sources=extra)
    assert not has_perm(user, "identity.user.create", target=campus_1a, extra_sources=extra)
    assert has_perm(
        user,
        "identity.user.create",
        target=ScopeTarget(TENANT_A, INST_2, CAMPUS_1B),
        extra_sources=extra,
    )
    assert not has_perm(
        user,
        "identity.user.view",
        target=ScopeTarget(TENANT_A, INST_1, CAMPUS_1B),
        extra_sources=extra,
    )
    assert not has_perm(
        user, "identity.user.view", target=ScopeTarget(TENANT_B), extra_sources=extra
    )
    assert not has_perm(user, "identity.user.view", extra_sources=extra)  # platform target


def test_object_policy_hook_can_narrow_a_grant():
    sa = make_user("sa@example.com", roles=("super_admin",)).user
    other = make_user("other@example.com").user
    engine.register_policy("identity.user", lambda actor, code, obj, target: obj.pk != actor.pk)
    try:
        assert has_perm(sa, "identity.user.view", obj=other)
        assert not has_perm(sa, "identity.user.view", obj=sa)
    finally:
        engine._POLICIES.clear()


def test_cache_is_invalidated_on_assignment_change():
    user = make_user("u@example.com").user
    assert not has_perm(user, "identity.user.view")
    role = Role.objects.get(code="platform_support", tenant_id__isnull=True)
    assignment = PlatformRoleAssignment.objects.create(
        user=user, role=role, granted_at=role.created_at
    )
    assert has_perm(user, "identity.user.view")
    assignment.delete()
    assert not has_perm(user, "identity.user.view")


def test_privileged_accounts_are_data_driven():
    assert not user_requires_mfa(make_user("plain@example.com").user)
    assert user_requires_mfa(make_user("s@example.com", roles=("platform_support",)).user)
    # platform_billing holds no Phase 2 permission yet, but every platform role requires MFA.
    assert user_requires_mfa(make_user("b@example.com", roles=("platform_billing",)).user)


def _role(code):
    return Role.objects.get(code=code, tenant_id__isnull=True, kind=RoleKind.PLATFORM)


def test_no_self_escalation_through_role_creation_or_grants():
    onboarding = make_user("on@example.com", roles=("platform_onboarding",)).user
    support_role = _role("platform_support")
    PlatformRoleAssignment.objects.create(
        user=onboarding, role=_role("super_admin"), granted_at=support_role.created_at
    )
    sa_holder = onboarding
    # A role-manager without audit permissions can't create a role containing them.
    manager = make_user("mgr@example.com").user
    custom = create_role(
        actor=sa_holder,
        code="role_manager",
        name="Role manager",
        permissions=["rbac.role.create", "rbac.platform_role.assign", "identity.user.view"],
    )
    grant_platform_role(actor=sa_holder, user=manager, role=custom, reason="testing")
    with pytest.raises(GuardRailViolation) as exc:
        create_role(actor=manager, code="sneaky", name="x", permissions=["audit.event.view_ip"])
    assert exc.value.code == "privilege_escalation"
    with pytest.raises(GuardRailViolation):
        grant_platform_role(actor=manager, user=manager, role=support_role, reason="escalate")
    with pytest.raises(GuardRailViolation):
        grant_platform_role(
            actor=manager, user=manager, role=_role("super_admin"), reason="escalate"
        )


def test_last_super_admin_cannot_be_demoted():
    sa = make_user("sa@example.com", roles=("super_admin",)).user
    assignment = PlatformRoleAssignment.objects.get(user=sa, role__code="super_admin")
    with pytest.raises(GuardRailViolation) as exc:
        revoke_platform_role(actor=sa, assignment=assignment)
    assert exc.value.code == "last_super_admin"
    second = make_user("sa2@example.com", roles=("super_admin",)).user
    revoke_platform_role(actor=second, assignment=assignment)
    assert not PlatformRoleAssignment.objects.filter(pk=assignment.pk).exists()


def test_system_roles_are_read_only():
    sa = make_user("sa@example.com", roles=("super_admin",)).user
    with pytest.raises(GuardRailViolation):
        update_role(actor=sa, role=_role("platform_support"), changes={"name": "x"})


def test_role_permission_tenant_id_follows_role_and_role_tenant_is_immutable(tenant_factory):
    from apps.core.tenancy import tenant_atomic

    ctx = tenant_factory()
    tenant = ctx.id
    perm = Permission.objects.get(code="identity.user.view")
    # Tenant roles are written inside their tenant (dual-scope RLS, Phase 3 M6).
    with tenant_atomic(ctx):
        role = Role.objects.create(tenant_id=tenant, code="t_role", name="T", kind=RoleKind.TENANT)
        rp = RolePermission.objects.create(role=role, permission=perm, tenant_id=None)
        rp.refresh_from_db()
        assert rp.tenant_id == tenant
        with pytest.raises(IntegrityError), transaction.atomic():
            Role.objects.filter(pk=role.pk).update(tenant_id=uuid.uuid4())
    # Outside the tenant the role does not exist, and the platform can't create one.
    assert not Role.objects.filter(pk=role.pk).exists()
    with pytest.raises(ProgrammingError, match="row-level security"), transaction.atomic():
        Role.objects.create(tenant_id=tenant, code="sneaky", name="S", kind=RoleKind.TENANT)


def test_role_kind_and_tenant_must_be_consistent():
    with pytest.raises((IntegrityError, DataError, InternalError)), transaction.atomic():
        Role.objects.create(tenant_id=None, code="bad", name="bad", kind=RoleKind.TENANT)
    with pytest.raises(IntegrityError), transaction.atomic():
        Role.objects.create(tenant_id=None, code="super_admin", name="dup", kind=RoleKind.PLATFORM)
