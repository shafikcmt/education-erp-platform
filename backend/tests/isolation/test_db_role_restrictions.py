"""Database role restrictions (ADR-043 §2, plan §5.3 #7): no runtime BYPASSRLS path."""

import pytest
from django.db import connection

pytestmark = pytest.mark.django_db

APP_ROLES = ("erp_app", "erp_owner")


def _one(sql: str, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, list(params))
        return cursor.fetchall()


def test_only_erp_platform_has_bypassrls_apart_from_cluster_superusers():
    """Superusers bypass RLS by definition; the cluster bootstrap superuser is never used by
    the application (runtime and migrations use erp_app / erp_owner, ADR-040 H3)."""
    rows = _one("SELECT rolname FROM pg_roles WHERE rolbypassrls AND NOT rolsuper ORDER BY rolname")
    assert rows == [("erp_platform",)]


def test_application_roles_are_neither_superuser_nor_bypassrls():
    rows = _one(
        "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = ANY(%s) ORDER BY 1",
        [list(APP_ROLES)],
    )
    assert rows == [("erp_app", False, False), ("erp_owner", False, False)]


def test_erp_platform_cannot_log_in_and_has_no_members():
    assert _one("SELECT rolcanlogin FROM pg_roles WHERE rolname = 'erp_platform'") == [(False,)]
    members = _one(
        "SELECT m.rolname FROM pg_auth_members am JOIN pg_roles m ON m.oid = am.member "
        "WHERE am.roleid = 'erp_platform'::regrole"
    )
    assert members == []


def test_application_roles_inherit_no_privileged_role():
    """Neither runtime nor owner role is a member (directly or transitively) of any role with
    superuser or BYPASSRLS, so SET ROLE can't reach one."""
    rows = _one(
        """
        WITH RECURSIVE granted(member, role) AS (
          SELECT am.member, am.roleid FROM pg_auth_members am
          WHERE am.member = ANY (SELECT oid FROM pg_roles WHERE rolname = ANY(%s))
          UNION
          SELECT g.member, am.roleid FROM granted g JOIN pg_auth_members am ON am.member = g.role
        )
        SELECT r.rolname FROM granted g JOIN pg_roles r ON r.oid = g.role
        WHERE r.rolsuper OR r.rolbypassrls
        """,
        [list(APP_ROLES)],
    )
    assert rows == []


def test_runtime_connection_is_erp_app_without_bypass():
    assert _one("SELECT current_user, session_user") == [("erp_app", "erp_app")]
    assert _one("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user") == [(False,)]
