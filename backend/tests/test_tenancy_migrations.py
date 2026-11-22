"""Phase 3 M2 migration rehearsal (plan §19.2): forward → reverse → forward on a throwaway
database with the real commands as the owner role, Phase 2 data untouched both ways, and
reversal refused unless explicitly allowed on a disposable database."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg
import pytest
from django.db import connection

BACKEND = Path(__file__).resolve().parents[1]

PHASE2_FINGERPRINT = """
SELECT
  (SELECT count(*) FROM rbac_permission),
  (SELECT count(*) FROM rbac_role),
  (SELECT count(*) FROM rbac_rolepermission),
  (SELECT count(*) FROM identity_user),
  (SELECT md5(string_agg(code || ':' || requires_mfa::text, ',' ORDER BY code))
     FROM rbac_permission),
  (SELECT md5(string_agg(code || ':' || kind, ',' ORDER BY code)) FROM rbac_role)
"""
TENANCY_OBJECTS = """
SELECT
  (SELECT count(*) FROM pg_class WHERE relname LIKE 'tenancy\\_%%' AND relkind = 'r'),
  (SELECT count(*) FROM pg_proc WHERE proname LIKE 'tenancy\\_%%')
"""


@pytest.mark.django_db
def test_tenancy_migrations_rehearse_forward_reverse_forward(owner_dsn):
    name = f"erp_rehearsal_{uuid.uuid4().hex[:8]}"
    host, port = owner_dsn["host"], owner_dsn["port"]
    with psycopg.connect(**owner_dsn, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}" TEMPLATE template1')
    owner_url = f"postgres://{owner_dsn['user']}:{owner_dsn['password']}@{host}:{port}/{name}"
    app_url = (
        f"postgres://{connection.settings_dict['USER']}:{connection.settings_dict['PASSWORD']}"
        f"@{host}:{port}/{name}"
    )
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.test",
        "DATABASE_MIGRATION_URL": owner_url,
        "DATABASE_URL": app_url,
    }

    def manage(*args: str, ok: bool = True, **extra: str) -> str:
        result = subprocess.run(  # noqa: S603 - fixed interpreter and arguments
            [sys.executable, "manage.py", *args],
            cwd=BACKEND,
            env={**env, **extra},
            capture_output=True,
            text=True,
            check=False,
            timeout=240,
        )
        output = result.stdout + result.stderr
        assert (result.returncode == 0) is ok, output
        return output

    def query(sql: str) -> tuple[object, ...]:
        with psycopg.connect(owner_url) as conn:
            row = conn.execute(sql).fetchone()
        assert row is not None
        return tuple(row)

    try:
        manage("migrate", "--noinput")
        manage("seed_roles")
        manage(
            "create_platform_admin",
            "--email",
            "rehearsal@example.test",
            DATABASE_MIGRATION_URL=app_url,
        )
        phase2 = query(PHASE2_FINGERPRINT)
        # 8 tables (sign-up requests since Phase 5 M8); F1-F3 + guard trigger function
        assert query(TENANCY_OBJECTS) == (8, 4)

        refused = manage("migrate", "tenancy", "zero", "--noinput", ok=False)
        assert "Refusing to reverse" in refused
        # Ordinary migrations after the isolation ones reverse until the guard refuses: the
        # sign-up registry table (0007, no RLS) is gone, every isolation object stays.
        assert query(TENANCY_OBJECTS) == (7, 4)

        manage("migrate", "tenancy", "zero", "--noinput", ERP_ALLOW_ISOLATION_ROLLBACK="true")
        assert query(TENANCY_OBJECTS) == (0, 0)
        assert query(PHASE2_FINGERPRINT) == phase2

        manage("migrate", "--noinput")
        assert query(TENANCY_OBJECTS) == (8, 4)
        assert query(PHASE2_FINGERPRINT) == phase2
        assert "No migrations to apply" in manage("migrate", "--noinput")
    finally:
        with psycopg.connect(**owner_dsn, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
