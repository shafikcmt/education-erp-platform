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
    # Every alias (including the Phase 3 test mirror) must use the same role.
    for alias in connections:
        conn = connections[alias]
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
        # Permission catalogue + system roles, exactly as the compose ``migrate`` bootstrap does:
        # as the OWNER role (O1: erp_app may only read rbac_permission).
        from apps.rbac.seeding import seed_roles, sync_permissions

        sync_permissions()
        seed_roles()
        from apps.module_registry.sync import sync_modules

        sync_modules()
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


# --------------------------------------------------------------------------- Phase 3 tenants
@pytest.fixture
def tenant_factory(db: Any) -> Any:
    """Create tenant registry rows in the test transaction (``make_tenant``)."""
    from tests.isolation.factories import make_tenant

    return make_tenant


@pytest.fixture
def committed_tenant_pair(owner_dsn: dict[str, Any]) -> Iterator[Any]:
    """Two committed tenants for worker-thread tests; rows removed afterwards."""
    from tests.isolation.factories import committed_tenants

    with committed_tenants(owner_dsn, 2) as tenants:
        yield tenants


@pytest.fixture
def tenant_hosts(settings: Any) -> None:
    """Switch tenant hosts on (they are off by default in every settings module, D1) and add
    the test-only probe endpoints used to exercise the tenant request path."""
    settings.TENANT_HOSTS_ENABLED = True
    settings.ROOT_URLCONF = "tests.isolation_app.urls"


@pytest.fixture
def tenant_site(tenant_hosts: None, db: Any) -> Any:
    """Factory for tenants that F1 can resolve (``make_tenant_site``)."""
    from tests.isolation.factories import make_tenant_site

    return make_tenant_site


@pytest.fixture
def committed_tenant_sites(tenant_hosts: None, owner_dsn: dict[str, Any]) -> Iterator[Any]:
    """Three committed, resolvable tenants for worker-thread request tests."""
    from tests.isolation.factories import committed_tenants

    with committed_tenants(owner_dsn, 3, sites=True) as tenants:
        yield tenants


@pytest.fixture(autouse=True)
def _guarded_email(settings: Any) -> None:
    """pytest-django replaces EMAIL_BACKEND with locmem; keep the guarded one (Phase 3 M7):
    sending email inside an open tenant transaction fails every test that does it."""
    settings.EMAIL_BACKEND = "apps.core.testing.GuardedLocmemEmailBackend"


@pytest.fixture
def org(tenant_site: Any) -> Any:
    """One tenant with two institutions, three campuses and four members (Phase 3 M4)."""
    from types import SimpleNamespace

    from apps.core.tenancy import tenant_atomic
    from apps.rbac.engine import ScopeTarget
    from apps.tenancy.models import Campus, Institution
    from tests.helpers import make_user
    from tests.isolation.factories import grant_role, seed_tenant_roles

    tenant = tenant_site(slug="acme")
    seed_tenant_roles(tenant)
    with tenant_atomic(tenant):
        north = Institution.objects.create(code="north", name="North", institution_type="school")
        south = Institution.objects.create(code="south", name="South", institution_type="madrasa")
        main = Campus.objects.create(institution=north, code="main", name="Main", is_main=True)
        annex = Campus.objects.create(institution=north, code="annex", name="Annex")
        south_main = Campus.objects.create(
            institution=south, code="main", name="South main", is_main=True
        )
    owner = make_user("owner@example.com").user
    head = make_user("head@example.com").user
    campus_admin = make_user("campus@example.com").user
    teacher = make_user("teacher@example.com").user
    grant_role(tenant, owner, "tenant_owner")
    grant_role(tenant, head, "institution_admin", institution=north)
    grant_role(tenant, campus_admin, "campus_admin", institution=north, campus=main)
    grant_role(tenant, teacher, "teacher", institution=north, campus=main)
    return SimpleNamespace(
        tenant=tenant,
        north=north,
        south=south,
        main=main,
        annex=annex,
        south_main=south_main,
        owner=owner,
        head=head,
        campus_admin=campus_admin,
        teacher=teacher,
        t_tenant=ScopeTarget(tenant.id),
        t_north=ScopeTarget(tenant.id, north.pk),
        t_south=ScopeTarget(tenant.id, south.pk),
        t_main=ScopeTarget(tenant.id, north.pk, main.pk),
        t_annex=ScopeTarget(tenant.id, north.pk, annex.pk),
        t_south_main=ScopeTarget(tenant.id, south.pk, south_main.pk),
    )
