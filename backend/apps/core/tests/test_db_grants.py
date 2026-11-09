"""Runtime-role privilege narrowing (Phase 2 plan §6.8): migrations history is read-only."""

import pytest
from django.db import connection, transaction
from django.db.utils import ProgrammingError

from apps.core.db_operations import RestrictTableGrants

pytestmark = pytest.mark.django_db


def test_runtime_role_can_read_but_not_write_migration_history():
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM django_migrations")
        assert cursor.fetchone()[0] > 0
    for sql in (
        "INSERT INTO django_migrations (app, name, applied) VALUES ('x', 'y', now())",
        "UPDATE django_migrations SET name = name",
        "DELETE FROM django_migrations",
    ):
        with (
            pytest.raises(ProgrammingError, match="permission denied"),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(sql)


def test_operation_rejects_unknown_privileges_and_deconstructs():
    with pytest.raises(ValueError, match="Unsupported"):
        RestrictTableGrants("t", ("TRUNCATE",))
    name, _args, kwargs = RestrictTableGrants("t", ("SELECT",)).deconstruct()
    assert (name, kwargs) == ("RestrictTableGrants", {"table": "t", "privileges": ("SELECT",)})


FRAMEWORK_READ_ONLY = (
    "auth_group",
    "auth_group_permissions",
    "auth_permission",
    "django_content_type",
)
USER_LINK_TABLES = ("identity_user_groups", "identity_user_user_permissions")


def _privileges(table: str) -> set[str]:
    granted = set()
    with connection.cursor() as cursor:
        for priv in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
            cursor.execute("SELECT has_table_privilege('erp_app', %s, %s)", [table, priv])
            if cursor.fetchone()[0]:
                granted.add(priv)
    return granted


def test_framework_tables_are_read_only_for_runtime_role():
    """M1: written only by ``migrate`` (owner); unused for authorization (ADR-033)."""
    for table in FRAMEWORK_READ_ONLY:
        assert _privileges(table) == {"SELECT"}, table
    with connection.cursor() as cursor, pytest.raises(ProgrammingError, match="permission denied"):
        with transaction.atomic():
            cursor.execute("INSERT INTO auth_group (name) VALUES ('rogue')")


def test_user_link_tables_allow_only_select_and_delete():
    """M1: user deletion removes (empty) link rows; nothing ever inserts or updates them."""
    for table in USER_LINK_TABLES:
        assert _privileges(table) == {"SELECT", "DELETE"}, table


def test_session_table_keeps_full_dml():
    assert _privileges("django_session") == {"SELECT", "INSERT", "UPDATE", "DELETE"}
