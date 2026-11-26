"""Tenant-aware RBAC (Phase 3 M4; plan §4.4, §9; ADR-044): role assignments, system role
copies, the tenant permission source, the per-template matrix and the guard rails.
Runs as ``erp_app``."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.core.ids import new_id
from apps.core.tenancy import TenantContextMissing, tenant_atomic
from apps.rbac import tenant_roles
from apps.rbac.engine import (
    PLATFORM,
    ScopeTarget,
    bump_tenant_version,
    effective_permissions,
    has_perm,
    tenant_cache_version,
    user_requires_mfa,
)
from apps.rbac.models import Role, RoleAssignment, RoleKind, RolePermission
from apps.rbac.role_templates import SUSPENDED_OWNER_CODES, TEMPLATE_ROLES
from apps.rbac.services import GuardRailViolation
from apps.rbac.sources import SELF_SERVICE_CODES, PlatformRoleSource
from apps.tenancy.models import Campus, Institution, Membership, Tenant
from apps.tenancy.rules import TenantStatus
from apps.tenancy.services import assignments, memberships
from apps.tenancy.services.system_roles import sync_all_tenants
from tests.helpers import make_user
from tests.isolation.factories import (
    add_member,
    grant_role,
    role_codes,
    seed_tenant_roles,
    system_role,
    tenant_events,
)

pytestmark = pytest.mark.django_db
SELF = SELF_SERVICE_CODES
TEMPLATE_CODES = [row["code"] for row in TEMPLATE_ROLES]


# Phase 6: teachers also read the academic structure.
TEACHER_CODES = {
    "tenancy.tenant.view",
    "academics.structure.view",
    "academics.subject.view",
    "academics.offering.view",
    "students.student.view_assigned",  # Phase 7 (ADR-073)
    "staff.profile.view_own",  # Phase 7 M3
}


def _perms(tenant, user, target: ScopeTarget | None = None, *, cache: bool = False) -> frozenset:
    with tenant_atomic(tenant):
        return effective_permissions(
            user, target or ScopeTarget(tenant_id=tenant.id), use_cache=cache
        )


def _codes(tenant, template_code: str) -> set[str]:
    return role_codes(system_role(tenant.id, template_code))


def _membership(org, user) -> Membership:
    with tenant_atomic(org.tenant):
        return Membership.objects.get(user=user)


# --------------------------------------------------------------------------- database keys
EXPECTED_FKS = {
    "rbac_assignment_membership_fk": (["tenant_id", "membership_id"], "tenancy_membership"),
    "rbac_assignment_role_fk": (["tenant_id", "role_id"], "rbac_role"),
    "rbac_assignment_institution_fk": (["tenant_id", "institution_id"], "tenancy_institution"),
    "rbac_assignment_campus_fk": (
        ["tenant_id", "institution_id", "campus_id"],
        "tenancy_campus",
    ),
}
INSERT_ASSIGNMENT = (
    "INSERT INTO rbac_roleassignment (id, created_at, updated_at, tenant_id, membership_id, "
    "role_id, scope_type, institution_id, campus_id, valid_from, reason) "
    "VALUES (%s, now(), now(), %s, %s, %s, %s, %s, %s, now(), '')"
)


def _sqlstate(sql: str, params: list[Any]) -> str:
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql, params)
    except IntegrityError as exc:
        return getattr(exc.__cause__, "sqlstate", "") or "integrity"
    return ""


def test_assignment_keys_are_composite_restrict_and_the_only_foreign_keys():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT con.conname, dst.relname, con.confmatchtype::text, con.confdeltype::text,
                   con.condeferrable,
              ARRAY(SELECT a.attname FROM unnest(con.conkey) WITH ORDINALITY k(n, o)
                    JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.n
                    ORDER BY k.o)
            FROM pg_constraint con JOIN pg_class dst ON dst.oid = con.confrelid
            WHERE con.contype = 'f' AND con.conrelid = 'rbac_roleassignment'::regclass
            """
        )
        rows = {r[0]: r for r in cursor.fetchall()}
    tenant_fk = {name for name, row in rows.items() if row[1] == "tenancy_tenant"}
    assert len(tenant_fk) == 1  # the registry reference of every tenant table
    assert set(rows) - tenant_fk == set(EXPECTED_FKS)
    for name, (columns, table) in EXPECTED_FKS.items():
        _, dst, match, delete, deferrable, cols = rows[name]
        assert (dst, cols, match, delete, deferrable) == (table, columns, "s", "r", False), name


def test_cross_tenant_and_template_references_are_impossible(org, tenant_site):
    other = tenant_site(slug="bravo")
    seed_tenant_roles(other)
    with tenant_atomic(other):
        other_inst = Institution.objects.create(code="x", name="X", institution_type="school")
        other_campus = Campus.objects.create(institution=other_inst, code="c", name="C")
    stranger = add_member(other, make_user("stranger@example.com").user)
    other_role = system_role(other.id, "teacher")
    template = Role.objects.get(kind=RoleKind.TEMPLATE, code="teacher")
    platform = Role.objects.get(kind=RoleKind.PLATFORM, code="super_admin")
    mine = _membership(org, org.teacher)
    role = system_role(org.tenant.id, "teacher")
    t = org.tenant.id

    def insert(membership, role_id, scope, inst=None, campus=None) -> str:
        return _sqlstate(INSERT_ASSIGNMENT, [new_id(), t, membership, role_id, scope, inst, campus])

    with tenant_atomic(org.tenant):
        assert insert(stranger.pk, role.pk, "tenant") == "23503"  # other tenant's member
        assert insert(mine.pk, other_role.pk, "tenant") == "23503"  # other tenant's role
        assert insert(mine.pk, template.pk, "tenant") == "23503"  # a template
        assert insert(mine.pk, platform.pk, "tenant") == "23503"  # a platform role
        assert insert(mine.pk, role.pk, "institution", other_inst.pk) == "23503"
        assert insert(mine.pk, role.pk, "campus", other_inst.pk, other_campus.pk) == "23503"
        # A campus of another institution of the SAME tenant.
        assert insert(mine.pk, role.pk, "campus", org.south.pk, org.main.pk) == "23503"
        # No oracle: a random id fails exactly like a foreign one.
        assert insert(mine.pk, new_id(), "tenant") == "23503"
        # Scope CHECK makes the right keys mandatory.
        assert insert(mine.pk, role.pk, "tenant", org.north.pk) == "23514"
        assert insert(mine.pk, role.pk, "institution") == "23514"
        assert insert(mine.pk, role.pk, "campus", org.north.pk) == "23514"
        # Control, and the one-live-assignment rule.
        assert insert(mine.pk, role.pk, "campus", org.north.pk, org.annex.pk) == ""
        assert insert(mine.pk, role.pk, "campus", org.north.pk, org.annex.pk) == "23505"


def test_assignments_are_invisible_to_other_tenants(org, tenant_site):
    other = tenant_site(slug="bravo")
    with tenant_atomic(other), connection.cursor() as cursor:
        assert not RoleAssignment.objects.exists()
        cursor.execute("SELECT count(*) FROM rbac_roleassignment")
        assert cursor.fetchone()[0] == 0
    with tenant_atomic(org.tenant):
        assert RoleAssignment.objects.count() == 4


def test_referenced_rows_cannot_be_deleted(org):
    with tenant_atomic(org.tenant):
        for model, pk in ((Membership, _membership(org, org.teacher).pk), (Campus, org.main.pk)):
            with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as c:
                c.execute(f"DELETE FROM {model._meta.db_table} WHERE id = %s", [pk])


# --------------------------------------------------------------------------- system copies
def test_system_copies_mirror_the_templates_and_are_read_only(org):
    t = org.tenant.id
    with tenant_atomic(org.tenant):
        copies = tenant_roles.tenant_roles(t)
        assert sorted(copies.values_list("code", flat=True)) == sorted(TEMPLATE_CODES)
        for copy in copies.select_related("template"):
            assert copy.is_system and copy.kind == RoleKind.TENANT and copy.tenant_id == t
            template = copy.template
            assert template is not None and template.kind == RoleKind.TEMPLATE
            assert tenant_roles.role_codes(copy) == tenant_roles.role_codes(template)
        assert not tenant_roles.sync_system_copies(t).changed  # idempotent
    # Outside the tenant (platform context) its roles don't exist: RLS (M6).
    assert not tenant_roles.tenant_roles(t).exists()
    owner_codes = _codes(org.tenant, "tenant_owner")
    assert {"tenancy.member.remove", "rbac.assignment.manage", "rbac.role.clone"} <= owner_codes
    assert _codes(org.tenant, "institution_admin") < owner_codes
    assert _codes(org.tenant, "campus_admin") < _codes(org.tenant, "institution_admin")
    assert _codes(org.tenant, "teacher") == TEACHER_CODES


def test_template_reference_must_be_a_template(org):
    platform = Role.objects.get(kind=RoleKind.PLATFORM, code="super_admin")
    copy = system_role(org.tenant.id, "teacher")
    template = Role.objects.get(kind=RoleKind.TEMPLATE, code="teacher")
    with tenant_atomic(org.tenant):
        for bad in (platform.pk, copy.pk, new_id()):
            with pytest.raises(IntegrityError, match="template"), transaction.atomic():
                Role.objects.filter(pk=copy.pk).update(template_id=bad)
        # Only a tenant's system copy may carry a template, and only one copy per template.
        with (
            pytest.raises(IntegrityError, match="template_only_on_system_copy"),
            transaction.atomic(),
        ):
            Role.objects.create(
                tenant_id=org.tenant.id, kind="tenant", code="custom", name="C", template=template
            )
        with pytest.raises(IntegrityError, match="one_copy_per_template"), transaction.atomic():
            Role.objects.create(
                tenant_id=org.tenant.id,
                kind="tenant",
                code="teacher-two",
                name="T",
                is_system=True,
                template=template,
            )


def test_p7_syncs_every_tenant_and_isolates_failures(org, tenant_site, monkeypatch):
    other = tenant_site(slug="bravo")
    seed_tenant_roles(other)
    gone = tenant_site(slug="charlie", status=TenantStatus.DELETED)
    template = Role.objects.get(kind=RoleKind.TEMPLATE, code="teacher")
    extra = template.role_permissions.model.objects.create(
        role=template, permission_id=_permission_id("tenancy.member.view")
    )
    versions = {t.id: tenant_cache_version(t.id) for t in (org.tenant, other)}
    summary = sync_all_tenants()
    assert (summary.tenants, summary.changed, summary.failed) == (2, 2, 0)
    for tenant in (org.tenant, other):
        assert _codes(tenant, "teacher") == TEACHER_CODES | {"tenancy.member.view"}
        assert tenant_cache_version(tenant.id) != versions[tenant.id]
    with tenant_atomic(gone):
        assert not Role.objects.filter(tenant_id=gone.id).exists()
    assert sync_all_tenants().changed == 0  # idempotent
    # A failure in one tenant never stops the others.
    extra.delete()
    real = tenant_roles.sync_system_copies

    def flaky(tenant_id):
        if tenant_id == org.tenant.id:
            raise RuntimeError("boom")
        return real(tenant_id)

    monkeypatch.setattr("apps.tenancy.services.system_roles.sync_system_copies", flaky)
    summary = sync_all_tenants()
    assert (summary.tenants, summary.changed, summary.failed) == (2, 1, 1)
    assert _codes(other, "teacher") == TEACHER_CODES
    assert _codes(org.tenant, "teacher") == TEACHER_CODES | {"tenancy.member.view"}


def _permission_id(code: str) -> Any:
    from apps.rbac.models import Permission

    return Permission.objects.get(code=code).pk


def test_clone_is_editable_never_synced_and_needs_the_permissions(org):
    source = system_role(org.tenant.id, "institution_admin")
    with tenant_atomic(org.tenant):
        with pytest.raises(PermissionDenied):
            tenant_roles.clone_role(
                actor=org.head, tenant_id=org.tenant.id, source=source, code="x", name="X"
            )
        clone = tenant_roles.clone_role(
            actor=org.owner,
            tenant_id=org.tenant.id,
            source=source,
            code="deputy-head",
            name="Deputy head",
        )
        assert (clone.is_system, clone.template_id, clone.tenant_id) == (
            False,
            None,
            org.tenant.id,
        )
        assert tenant_roles.role_codes(clone) == tenant_roles.role_codes(source)
        with pytest.raises(ValidationError):
            tenant_roles.clone_role(
                actor=org.owner,
                tenant_id=org.tenant.id,
                source=source,
                code="deputy-head",
                name="Again",
            )
        template = Role.objects.get(kind=RoleKind.TEMPLATE, code="teacher")
        with pytest.raises(ValidationError):
            tenant_roles.clone_role(
                actor=org.owner, tenant_id=org.tenant.id, source=template, code="t2", name="T"
            )
        RolePermission.objects.filter(role=clone).delete()
        assert not tenant_roles.sync_system_copies(org.tenant.id).changed
        assert tenant_roles.role_codes(clone) == set()


# --------------------------------------------------------------------------- matrix
@pytest.mark.parametrize("template_code", TEMPLATE_CODES)
def test_rbac_matrix_per_template_at_tenant_scope(org, template_code):
    """A member holding only this role, tenant-wide, gets exactly its permissions (plus the
    self-service codes) in every scope of this tenant, and nothing on the platform."""
    user = make_user(f"matrix-{template_code}@example.com").user
    grant_role(org.tenant, user, template_code)
    expected = _codes(org.tenant, template_code) | SELF
    for target in (org.t_tenant, org.t_north, org.t_main, org.t_south_main):
        assert _perms(org.tenant, user, target) == expected, target
    assert effective_permissions(user, PLATFORM, use_cache=False) == SELF


def test_scopes_cover_downwards_and_never_sideways(org):
    head, campus = _codes(org.tenant, "institution_admin"), _codes(org.tenant, "campus_admin")
    expectations = {
        org.head: {
            org.t_north: head,
            org.t_main: head,
            org.t_annex: head,
            org.t_tenant: set(),
            org.t_south: set(),
            org.t_south_main: set(),
        },
        org.campus_admin: {
            org.t_main: campus,
            org.t_annex: set(),
            org.t_north: set(),
            org.t_tenant: set(),
            org.t_south_main: set(),
        },
    }
    for user, table in expectations.items():
        for target, codes in table.items():
            assert _perms(org.tenant, user, target) == codes | SELF, (user.email, target)


def test_several_assignments_are_unioned_per_scope(org):
    grant_role(org.tenant, org.campus_admin, "institution_admin", institution=org.south)
    assert _perms(org.tenant, org.campus_admin, org.t_south_main) == (
        _codes(org.tenant, "institution_admin") | SELF
    )
    assert _perms(org.tenant, org.campus_admin, org.t_main) == (
        _codes(org.tenant, "campus_admin") | SELF
    )
    assert _perms(org.tenant, org.campus_admin, org.t_annex) == SELF


def test_platform_roles_grant_nothing_in_a_tenant(org):
    """Plan §9.2: ``PlatformRoleSource`` yields nothing for a tenant target; a Super Admin who
    is also a member gets only what the tenant role gives."""
    admin = make_user("root@example.com", roles=("super_admin",), mfa=True).user
    assert PlatformRoleSource().grants(admin, org.t_tenant) == frozenset()
    assert _perms(org.tenant, admin) == SELF
    grant_role(org.tenant, admin, "teacher")
    assert _perms(org.tenant, admin) == SELF | TEACHER_CODES
    assert "rbac.assignment.manage" in effective_permissions(admin, PLATFORM, use_cache=False)


# --------------------------------------------------------------------------- fail closed
def test_grants_exist_only_inside_the_right_tenant_transaction(org, tenant_site):
    other = tenant_site(slug="bravo")
    seed_tenant_roles(other)
    owner_codes = _codes(org.tenant, "tenant_owner")
    assert _perms(org.tenant, org.owner) == owner_codes | SELF
    # No transaction for that tenant: nothing (and nothing is cached as a grant).
    assert effective_permissions(org.owner, org.t_tenant, use_cache=False) == SELF
    with tenant_atomic(other):
        assert effective_permissions(org.owner, org.t_tenant, use_cache=False) == SELF
        assert effective_permissions(org.owner, ScopeTarget(other.id), use_cache=False) == SELF
    assert not has_perm(org.owner, "tenancy.member.view", target=org.t_tenant, use_cache=False)


@pytest.mark.parametrize("status", ["invited", "suspended", "left"])
def test_inactive_memberships_grant_nothing(org, status):
    with tenant_atomic(org.tenant):
        Membership.objects.filter(user=org.owner).update(status=status)
    assert _perms(org.tenant, org.owner) == SELF


def test_assignment_validity_window_and_revocation(org):
    now = timezone.now()
    owner_codes = _codes(org.tenant, "tenant_owner") | SELF

    def window(**fields) -> frozenset:
        with tenant_atomic(org.tenant):
            RoleAssignment.objects.filter(membership__user=org.owner).update(**fields)
        return _perms(org.tenant, org.owner)

    assert window(valid_from=now + timedelta(hours=1)) == SELF  # not yet valid
    assert window(valid_from=now - timedelta(hours=2), valid_until=now - timedelta(hours=1)) == SELF
    assert window(valid_until=now + timedelta(hours=1)) == owner_codes
    assert window(valid_until=None, revoked_at=now) == SELF
    with pytest.raises(IntegrityError, match="rbac_assignment_validity"), tenant_atomic(org.tenant):
        RoleAssignment.objects.filter(membership__user=org.owner).update(
            valid_until=now - timedelta(days=9)
        )


def test_tenant_status_gates_all_grants(org):
    row = Tenant.objects.get(pk=org.tenant.id)

    def set_status(*statuses: str) -> None:
        for status in statuses:
            row.status = status
            row.save()

    set_status(TenantStatus.SUSPENDED)
    # Restricted owner mode (D2, M5): owners keep only the support-session review codes.
    assert _perms(org.tenant, org.owner) == SELF | SUSPENDED_OWNER_CODES
    assert _perms(org.tenant, org.head, org.t_north) == SELF
    # Offboarding: only owners keep their grants (the request gate refuses every write).
    set_status(TenantStatus.OFFBOARDING)
    assert _perms(org.tenant, org.owner) == _codes(org.tenant, "tenant_owner") | SELF
    assert _perms(org.tenant, org.head, org.t_north) == SELF
    set_status(TenantStatus.SUSPENDED, TenantStatus.ACTIVE)
    assert _perms(org.tenant, org.head, org.t_north) != SELF


# --------------------------------------------------------------------------- guard rails
def _grant(org, actor, user, template_code, scope, institution=None, campus=None):
    with tenant_atomic(org.tenant):
        membership = Membership.objects.filter(user=user).first() or Membership.objects.create(
            user=user, status="active"
        )
        return assignments.grant_assignment(
            actor=actor,
            membership=membership,
            role=system_role(org.tenant.id, template_code),
            scope_type=scope,
            institution=institution,
            campus=campus,
        )


def test_nobody_grants_outside_their_scope_or_above_their_permissions(org):
    new = make_user("new@example.com").user
    # A campus admin manages assignments in the own campus only.
    assert _grant(org, org.campus_admin, new, "teacher", "campus", org.north, org.main)
    for scope, inst, campus in (
        ("campus", org.north, org.annex),
        ("institution", org.north, None),
        ("tenant", None, None),
        ("campus", org.south, org.south_main),
    ):
        with pytest.raises(PermissionDenied):
            _grant(org, org.campus_admin, new, "teacher", scope, inst, campus)
    # In scope, but the role holds more than the actor does there.
    for actor, role, scope, inst, campus in (
        (org.campus_admin, "institution_admin", "campus", org.north, org.main),
        (org.campus_admin, "tenant_owner", "campus", org.north, org.main),
        (org.head, "tenant_owner", "institution", org.north, None),
    ):
        with pytest.raises(GuardRailViolation) as exc:
            _grant(org, actor, new, role, scope, inst, campus)
        assert exc.value.code == "privilege_escalation"
    # A teacher has no assignment permission at all.
    with pytest.raises(PermissionDenied):
        _grant(org, org.teacher, new, "teacher", "campus", org.north, org.main)
    assert _grant(org, org.head, new, "campus_admin", "campus", org.north, org.annex)
    assert _grant(org, org.owner, new, "institution_admin", "institution", org.south)


def test_only_roles_and_scopes_of_this_tenant_can_be_granted(org, tenant_site):
    other = tenant_site(slug="bravo")
    seed_tenant_roles(other)
    with tenant_atomic(other):
        foreign = Institution.objects.create(code="f", name="F", institution_type="school")
    membership = _membership(org, org.teacher)
    bad_roles = [
        Role.objects.get(kind=RoleKind.TEMPLATE, code="teacher"),
        Role.objects.get(kind=RoleKind.PLATFORM, code="super_admin"),
        system_role(other.id, "teacher"),
    ]
    good = system_role(org.tenant.id, "teacher")
    with tenant_atomic(org.tenant):
        for role in bad_roles:
            with pytest.raises(ValidationError):
                assignments.grant_assignment(
                    actor=org.owner, membership=membership, role=role, scope_type="tenant"
                )
        for scope, inst, campus in (
            ("institution", foreign.pk, None),  # another tenant's institution
            ("institution", new_id(), None),  # ... fails like a random id
            ("campus", org.south.pk, org.main.pk),  # campus of another institution
            ("tenant", org.north.pk, None),
            ("campus", org.north.pk, None),
            ("nonsense", None, None),
        ):
            with pytest.raises(ValidationError):
                assignments.grant_assignment(
                    actor=org.owner,
                    membership=membership,
                    role=good,
                    scope_type=scope,
                    institution=inst,
                    campus=campus,
                )


def test_grant_and_revoke_are_audited_idempotent_and_effective_at_once(org):

    new = make_user("new@example.com").user
    first = _grant(org, org.owner, new, "institution_admin", "institution", org.north)
    again = _grant(org, org.owner, new, "institution_admin", "institution", org.north)
    assert first.pk == again.pk
    # Cached read: the tenant version bump makes the change visible immediately.
    assert "tenancy.campus.create" in _perms(org.tenant, new, org.t_main, cache=True)
    with tenant_atomic(org.tenant):
        with pytest.raises(PermissionDenied):  # a campus admin has no say at this scope
            assignments.revoke_assignment(actor=org.campus_admin, assignment=first)
        revoked = assignments.revoke_assignment(actor=org.owner, assignment=first)
        assert revoked.revoked_at is not None and revoked.revoked_by == org.owner.pk
        assert assignments.revoke_assignment(actor=org.owner, assignment=first).pk == first.pk
    assert _perms(org.tenant, new, org.t_main, cache=True) == SELF
    events = tenant_events(org.tenant, action__startswith="rbac.assign")
    assert sorted((e.action, e.metadata["role_code"]) for e in events) == [
        ("rbac.assignment.granted", "institution_admin"),
        ("rbac.assignment.granted", "institution_admin"),
        ("rbac.assignment.revoked", "institution_admin"),
    ]
    with pytest.raises(TenantContextMissing):  # no tenant context: fail closed
        RoleAssignment.objects.filter(pk=first.pk).exists()
    with tenant_atomic(org.tenant):
        assert RoleAssignment.objects.filter(pk=first.pk).exists()  # history is kept


def test_the_last_active_owner_cannot_be_demoted_suspended_or_removed(org):
    second = make_user("second@example.com").user
    owner_m = _membership(org, org.owner)
    with tenant_atomic(org.tenant):
        only = RoleAssignment.objects.get(membership=owner_m)
        with pytest.raises(GuardRailViolation) as exc:
            assignments.revoke_assignment(actor=org.owner, assignment=only)
        assert exc.value.code == "last_tenant_owner"
    grant_role(org.tenant, second, "tenant_owner")
    second_m = _membership(org, second)
    with tenant_atomic(org.tenant):
        for action in (memberships.suspend_member, memberships.remove_member):
            with pytest.raises(GuardRailViolation) as exc:
                action(actor=org.owner, membership=owner_m)
            assert exc.value.code == "cannot_act_on_self"
        # With two owners, one may go ...
        memberships.suspend_member(actor=org.owner, membership=second_m)
        # ... and then the remaining one is the last again (a suspended owner doesn't count).
        with pytest.raises(GuardRailViolation) as exc:
            assignments.revoke_assignment(actor=org.owner, assignment=only)
        assert exc.value.code == "last_tenant_owner"
        memberships.reactivate_member(actor=org.owner, membership=second_m)
        assignments.revoke_assignment(actor=second, assignment=only)
        # The demoted former owner has no say any more; the new sole owner is protected too.
        with pytest.raises(PermissionDenied):
            memberships.remove_member(actor=org.owner, membership=second_m)
        second_only = RoleAssignment.objects.get(membership=second_m, revoked_at__isnull=True)
        with pytest.raises(GuardRailViolation) as exc:
            assignments.revoke_assignment(actor=second, assignment=second_only)
        assert exc.value.code == "last_tenant_owner"
    assert _perms(org.tenant, org.owner) == SELF


def test_acting_on_a_member_needs_every_permission_that_member_holds(org):
    owner_m, head_m, teacher_m = (_membership(org, u) for u in (org.owner, org.head, org.teacher))
    grant_role(org.tenant, org.head, "institution_admin")  # now tenant-wide: may update members
    with tenant_atomic(org.tenant):
        with pytest.raises(GuardRailViolation) as exc:
            memberships.suspend_member(actor=org.head, membership=owner_m)
        assert exc.value.code == "insufficient_privilege"
        with pytest.raises(PermissionDenied):  # institution admins can't remove members
            memberships.remove_member(actor=org.head, membership=teacher_m)
        with pytest.raises(PermissionDenied):
            memberships.suspend_member(actor=org.teacher, membership=head_m)
        assert (
            memberships.suspend_member(actor=org.head, membership=teacher_m).status == "suspended"
        )
        assert (
            memberships.reactivate_member(actor=org.head, membership=teacher_m).status == "active"
        )
        removed = memberships.remove_member(actor=org.owner, membership=head_m)
        assert removed.status == "left"
        assert not RoleAssignment.objects.filter(
            membership=head_m, revoked_at__isnull=True
        ).exists()
        with pytest.raises(ValidationError):
            assignments.grant_assignment(
                actor=org.owner,
                membership=removed,
                role=system_role(org.tenant.id, "teacher"),
                scope_type="tenant",
            )
    assert _perms(org.tenant, org.head, org.t_north) == SELF


# --------------------------------------------------------------------------- cache and MFA
def test_tenant_cache_versions_are_independent(org, tenant_site):
    other = tenant_site(slug="bravo")
    a, b = tenant_cache_version(org.tenant.id), tenant_cache_version(other.id)
    assert a != b and tenant_cache_version(org.tenant.id) == a
    bump_tenant_version(org.tenant.id)
    assert tenant_cache_version(org.tenant.id) != a
    assert tenant_cache_version(other.id) == b


def test_privileged_tenant_roles_require_mfa_in_their_tenant_only(org):
    with tenant_atomic(org.tenant):
        assert user_requires_mfa(org.owner, use_cache=False, target=org.t_tenant) is True
        assert user_requires_mfa(org.teacher, use_cache=False, target=org.t_main) is False
    assert user_requires_mfa(org.owner, use_cache=False) is False  # platform: no privileges
