"""``platform_scope`` foundation (Phase 3 M1; ADR-043, plan §6.3-§6.4)."""

import pytest
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.core.ids import new_id
from apps.core.tenancy import (
    PlatformScopeError,
    TenantContextConflict,
    bind_tenant,
    current_tenant,
    tenant_atomic,
)
from apps.core.tenancy.platform import CATALOGUE, SYSTEM, PlatformOperation, platform_scope
from apps.rbac.engine import has_perm
from apps.rbac.models import PlatformRoleAssignment
from tests.helpers import make_user

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _since() -> None:
    """Audit rows are append-only and some suites commit real ones in worker threads, so these
    tests only look at the events written during the test itself."""
    global _STARTED
    _STARTED = timezone.now()


_STARTED = None


def _events(action: str) -> list[AuditEvent]:
    return list(
        AuditEvent.objects.filter(action=action, occurred_at__gte=_STARTED).order_by("occurred_at")
    )


def test_catalogue_matches_plan_and_disables_what_phase_3_forbids():
    # P1-P16: Phase 3 plan §6.3; P17-P20: Phase 4 plan §5 (ADR-051); P21-P25: Phase 5 plan §7
    # and §13.8 (P25 added in M8; P23 enabled in M8, the feature itself is behind its flag).
    assert sorted(CATALOGUE, key=lambda k: int(k[1:])) == [f"P{i}" for i in range(1, 26)]
    disabled = {k for k, spec in CATALOGUE.items() if not spec.enabled}
    assert disabled == {"P3", "P11", "P15", "P16", "P20", "P21", "P22"}
    assert "D6" in CATALOGUE["P16"].disabled_reason  # no break-glass in Phase 3
    for spec in CATALOGUE.values():
        assert spec.mechanisms <= {"R", "T", "I", "D"}


@pytest.mark.parametrize("op", ["P99", "", "p1"])
def test_unknown_operations_are_refused(op):
    with (
        pytest.raises(PlatformScopeError, match="Unknown"),
        platform_scope(operation=op, actor=SYSTEM, reason="test run"),
    ):
        pass


@pytest.mark.parametrize("op", ["P3", "P11", "P15", "P16"])
def test_disabled_operations_are_refused(op):
    with (
        pytest.raises(PlatformScopeError, match="disabled"),
        platform_scope(operation=op, actor=SYSTEM, reason="test run"),
    ):
        pass


@pytest.mark.parametrize("reason", ["", "  ", "ab", "x" * 201])
def test_a_reason_is_required(reason):
    with (
        pytest.raises(PlatformScopeError, match="reason"),
        platform_scope(operation="P10", actor=SYSTEM, reason=reason),
    ):
        pass


def test_actor_kind_must_match_the_operation():
    user = make_user("ordinary@example.com").user
    with (
        pytest.raises(PlatformScopeError, match="system actor"),
        platform_scope(operation="P10", actor=user, reason="nightly run"),
    ):
        pass
    with (
        pytest.raises(PlatformScopeError, match="not the system actor"),
        platform_scope(
            operation="P9", actor=SYSTEM, reason="manual action", permission="identity.mfa.reset"
        ),
    ):
        pass
    from django.contrib.auth.models import AnonymousUser

    with (
        pytest.raises(PlatformScopeError, match="authenticated"),
        platform_scope(operation="P2", actor=AnonymousUser(), reason="my institutions"),
    ):
        pass


def test_refused_inside_a_tenant_context_and_when_nested():
    tid = new_id()
    with (
        tenant_atomic(tid),
        pytest.raises(TenantContextConflict),
        platform_scope(operation="P10", actor=SYSTEM, reason="nightly run"),
    ):
        pass
    with (
        bind_tenant(tid),
        pytest.raises(TenantContextConflict),
        platform_scope(operation="P10", actor=SYSTEM, reason="nightly run"),
    ):
        pass
    with platform_scope(operation="P10", actor=SYSTEM, reason="nightly run"):
        with (
            pytest.raises(PlatformScopeError, match="nested"),
            platform_scope(operation="P12", actor=SYSTEM, reason="inner"),
        ):
            pass


def test_system_iteration_is_audited_with_tenant_count_and_never_sets_a_tenant():
    tenants = [new_id(), new_id()]
    with platform_scope(operation="P10", actor=SYSTEM, reason="nightly IP anonymisation") as op:
        assert current_tenant() is None
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('app.tenant_id', true), current_user")
            setting, role = cursor.fetchone()
        assert (setting or "") == "" and role == "erp_app"  # no role change
        for tid in tenants:
            with tenant_atomic(tid):
                bound = current_tenant()
                assert bound is not None and bound.id == tid
        assert current_tenant() is None
    assert op.tenant_ids == set(tenants)
    started, completed = (
        _events("platform.operation.started"),
        _events("platform.operation.completed"),
    )
    assert len(started) == len(completed) == 1
    assert started[0].metadata == {
        "operation": "P10",
        "reason": "nightly IP anonymisation",
        "permission": "",
    }
    assert completed[0].metadata["tenant_count"] == 2 and completed[0].outcome == "success"
    assert completed[0].actor_type == "system" and completed[0].tenant_id is None


def test_failure_is_audited_and_the_error_propagates():
    with (
        pytest.raises(RuntimeError),
        platform_scope(operation="P10", actor=SYSTEM, reason="nightly run"),
    ):
        raise RuntimeError("boom")
    assert _events("platform.operation.completed")[0].outcome == "failure"


def test_tenant_transactions_only_for_operations_catalogued_for_them():
    with platform_scope(operation="P12", actor=SYSTEM, reason="housekeeping"):
        with pytest.raises(PlatformScopeError, match="not catalogued"), tenant_atomic(new_id()):
            pass
    assert _events("platform.operation.started") == []  # P12 is not audited by the scope


def test_targeted_operations_touch_only_one_tenant():
    handle = PlatformOperation(spec=CATALOGUE["P4"], actor=None, reason="x", permission=None)
    first = new_id()
    handle.touch(first)
    handle.touch(first)
    with pytest.raises(PlatformScopeError, match="one tenant"):
        handle.touch(new_id())


def test_user_operations_recheck_permission_without_cache(admin):
    reason = "deactivate a compromised account"
    with platform_scope(
        operation="P9", actor=admin.user, reason=reason, permission="identity.user.deactivate"
    ):
        pass
    assert _events("platform.operation.completed")[0].actor_user_id == admin.user.pk
    # Revoke the role behind the cache's back: cached checks still allow, the scope does not.
    assert has_perm(admin.user, "identity.user.deactivate")
    with connection.cursor() as cursor:  # raw SQL: no signal, so no cache-version bump
        cursor.execute(
            f"DELETE FROM {PlatformRoleAssignment._meta.db_table} WHERE user_id = %s",
            [admin.user.pk],
        )
    assert has_perm(admin.user, "identity.user.deactivate")  # stale cache
    with (
        pytest.raises(PermissionDenied),
        platform_scope(
            operation="P9", actor=admin.user, reason=reason, permission="identity.user.deactivate"
        ),
    ):
        pass


def test_permission_must_be_named_and_catalogued(admin):
    with (
        pytest.raises(PlatformScopeError, match="several actions"),
        platform_scope(operation="P9", actor=admin.user, reason="admin action"),
    ):
        pass
    with (
        pytest.raises(PlatformScopeError, match="not catalogued"),
        platform_scope(
            operation="P9", actor=admin.user, reason="admin action", permission="rbac.role.delete"
        ),
    ):
        pass


def test_ordinary_users_are_denied_and_nothing_runs():
    user = make_user("plain@example.com").user
    ran = []
    with (
        pytest.raises(PermissionDenied),
        platform_scope(
            operation="P9", actor=user, reason="try it", permission="identity.mfa.reset"
        ),
    ):
        ran.append(True)
    assert ran == [] and _events("platform.operation.started") == []


def test_registry_operations_fail_closed_without_their_permission(admin):
    """Since M8 every P4/P5/P6 code is registered: a user without it is refused before the
    scope starts (nothing is audited as started), a holder gets in."""
    from django.core.exceptions import PermissionDenied

    plain = make_user("plain@example.com").user
    for operation, permission in (
        ("P4", None),
        ("P5", "tenancy.tenant.suspend"),
        ("P6", None),
        ("P8", None),
    ):
        with (
            pytest.raises(PermissionDenied),
            platform_scope(operation=operation, actor=plain, reason="try", permission=permission),
        ):
            pass
    assert _events("platform.operation.started") == []
    with platform_scope(operation="P4", actor=admin.user, reason="provision acme") as op:
        assert op.permission == "tenancy.tenant.create"
    assert len(_events("platform.operation.started")) == 1


def test_own_account_and_anonymous_operations_need_no_permission(admin):
    with platform_scope(operation="P2", actor=admin.user, reason="my institutions") as op:
        assert op.permission is None
    with platform_scope(operation="P1", actor=None, reason="host resolution"):
        pass
    assert _events("platform.operation.started") == []  # P1/P2 are not audited per call
