"""Global pytest configuration.

ADR-009: the test database is created and migrated as ``erp_owner`` (see
``config.settings.test``), then every test runs as the runtime role ``erp_app`` — the same
NOSUPERUSER / NOBYPASSRLS / DML-only privileges as production. Without this, RLS tests in
later phases would silently pass under a privileged role.
"""

import os
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import environ
import pytest
from django.conf import settings
from django.db import connections

if TYPE_CHECKING:
    from tests.helpers import Api, Person


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
        # Mirror the production bootstrap (01-roles.sh): database ACLs are not inherited from
        # template1, so restrict CONNECT/TEMPORARY on the freshly created test database too.
        with connections["default"].cursor() as cursor:
            db = connections["default"].ops.quote_name(owner["NAME"])
            app = connections["default"].ops.quote_name(settings.TEST_APP_DB_USER)
            cursor.execute(f"REVOKE CONNECT, TEMPORARY ON DATABASE {db} FROM PUBLIC")
            cursor.execute(f"GRANT CONNECT ON DATABASE {db} TO {app}")
        _switch_default_connection(settings.TEST_APP_DB_USER, settings.TEST_APP_DB_PASSWORD)
        # Permission registry + system roles, as the compose ``migrate`` service does (as erp_app,
        # which has DML rights on these tables).
        from apps.rbac.seeding import seed_roles, sync_permissions

        sync_permissions()
        seed_roles()
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


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    """Throttle counters and permission caches must not leak between tests."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api() -> "Api":
    from tests.helpers import Api

    return Api()


@pytest.fixture
def admin(db: Any) -> "Person":
    """An active Super Admin with MFA enrolled."""
    from tests.helpers import make_user

    return make_user("admin@example.com", roles=("super_admin",), mfa=True)


@pytest.fixture
def admin_api(admin: "Person") -> "Api":
    """API client logged in as ``admin`` (MFA verified) and in fresh step-up mode."""
    from tests.helpers import Api

    client = Api()
    client.login(admin, expect="authenticated")
    client.step_up(admin)
    return client
