"""Global pytest configuration.

ADR-009: the test database is created and migrated as ``erp_owner`` (see
``config.settings.test``), then every test runs as the runtime role ``erp_app`` — the same
NOSUPERUSER / NOBYPASSRLS / DML-only privileges as production. Without this, RLS tests in
later phases would silently pass under a privileged role.
"""

import os
from collections.abc import Iterator
from typing import Any

import environ
import pytest
from django.conf import settings
from django.db import connections


def _switch_default_connection(user: str, password: str) -> None:
    conn = connections["default"]
    conn.close()
    conn.settings_dict["USER"] = user
    conn.settings_dict["PASSWORD"] = password


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup: Any, django_db_blocker: Any) -> Iterator[None]:
    """Run pytest-django's setup as the owner, then switch to ``erp_app`` for the tests."""
    owner = connections["default"].settings_dict
    owner_user, owner_password = owner["USER"], owner["PASSWORD"]
    with django_db_blocker.unblock():
        _switch_default_connection(settings.TEST_APP_DB_USER, settings.TEST_APP_DB_PASSWORD)
    yield
    with django_db_blocker.unblock():
        # Teardown (DROP DATABASE) needs the owner again.
        _switch_default_connection(owner_user, owner_password)


@pytest.fixture
def owner_dsn() -> dict[str, Any]:
    """psycopg connection kwargs for the *owner* role on the test database.

    Used only by tests that must perform DDL (e.g. creating a throwaway RLS-protected table);
    the application connection itself stays on ``erp_app``.
    """
    owner = environ.Env().db_url_config(os.environ["DATABASE_MIGRATION_URL"])
    return {
        "dbname": connections["default"].settings_dict["NAME"],
        "host": owner["HOST"] or "localhost",
        "port": owner["PORT"] or 5432,
        "user": owner["USER"],
        "password": owner["PASSWORD"],
    }
