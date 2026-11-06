"""Review H3: runtime processes refuse owner/superuser DB credentials (in-process unit tests;
the production settings module is also exercised end-to-end in test_settings.py)."""

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.core.config_guards import assert_runtime_has_no_owner_credentials

OWNERS = {"erp_owner", "postgres"}


@pytest.mark.parametrize(
    "environ",
    [
        {"DATABASE_MIGRATION_URL": "postgres://erp_owner:x@db/erp"},
        {"ERP_OWNER_PASSWORD": "x"},
        {"POSTGRES_PASSWORD": "x"},
    ],
)
def test_owner_credentials_in_runtime_env_are_refused(environ):
    with pytest.raises(ImproperlyConfigured, match="must not receive"):
        assert_runtime_has_no_owner_credentials(
            environ, database_user="erp_app", owner_roles=OWNERS
        )


@pytest.mark.parametrize("user", ["erp_owner", "postgres"])
def test_privileged_database_user_is_refused(user):
    with pytest.raises(ImproperlyConfigured, match="privileged database role"):
        assert_runtime_has_no_owner_credentials({}, database_user=user, owner_roles=OWNERS)


def test_runtime_role_and_migrate_process_are_allowed():
    assert_runtime_has_no_owner_credentials({}, database_user="erp_app", owner_roles=OWNERS)
    assert_runtime_has_no_owner_credentials(
        {"ERP_PROCESS_ROLE": "migrate", "DATABASE_MIGRATION_URL": "postgres://erp_owner:x@db/erp"},
        database_user="erp_owner",
        owner_roles=OWNERS,
    )
