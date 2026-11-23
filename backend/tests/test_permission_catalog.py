"""Permission catalogue is owner-controlled (Phase 3 M1, owner decision O1).

* ``erp_app`` can only SELECT ``rbac_permission`` (PostgreSQL grant, ``rbac.0003``).
* ``sync_permissions`` / ``seed_roles`` refuse to run as ``erp_app`` and are run by the
  owner-level ``migrate`` bootstrap; every run is audited.
* ``create_platform_admin`` runs as ``erp_app`` and only *checks* the catalogue.
* Seeding stays repeatable and idempotent (real commands, owner role, throwaway database).
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from io import StringIO
from pathlib import Path
from typing import Any

import psycopg
import pytest
import yaml
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.db.utils import ProgrammingError

from apps.audit.models import AuditEvent
from apps.identity.models import User
from apps.rbac.models import Permission, Role
from apps.rbac.seeding import catalog_drift, seed_roles, sync_permissions

pytestmark = pytest.mark.django_db

BACKEND = Path(__file__).resolve().parents[1]


def _denied(sql: str, params: list[Any]) -> bool:
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql, params)
    except ProgrammingError as exc:
        return "permission denied" in str(exc)
    return False


def test_runtime_role_can_only_read_the_permission_catalog():
    with connection.cursor() as cursor:
        for priv, expected in (
            ("SELECT", True),
            ("INSERT", False),
            ("UPDATE", False),
            ("DELETE", False),
            ("TRUNCATE", False),
        ):
            cursor.execute("SELECT has_table_privilege('erp_app', 'rbac_permission', %s)", [priv])
            assert cursor.fetchone()[0] is expected, priv
    some = Permission.objects.first()
    assert some is not None
    assert _denied(
        "INSERT INTO rbac_permission (id, created_at, updated_at, code, module_code, description, "
        "is_sensitive, requires_mfa, requires_step_up) "
        "VALUES (%s, now(), now(), 'rogue.thing.do', 'rogue', 'x', false, false, false)",
        [uuid.uuid4()],
    )
    assert _denied("UPDATE rbac_permission SET requires_mfa = false WHERE id = %s", [some.pk])
    assert _denied("DELETE FROM rbac_permission WHERE id = %s", [some.pk])
    with pytest.raises(ProgrammingError, match="permission denied"), transaction.atomic():
        Permission.objects.filter(pk=some.pk).update(description="changed")


def test_seeding_functions_and_commands_refuse_the_runtime_role():
    before = AuditEvent.objects.count()
    roles_before = list(Role.objects.values_list("id", "updated_at").order_by("id"))
    for fn in (sync_permissions, seed_roles):
        with pytest.raises(CommandError, match="must run as the database owner role"):
            fn()
    for command in ("sync_permissions", "seed_roles"):
        with pytest.raises(CommandError, match="must run as the database owner role"):
            call_command(command, stdout=StringIO())
    assert AuditEvent.objects.count() == before  # refused before touching anything
    assert list(Role.objects.values_list("id", "updated_at").order_by("id")) == roles_before


def test_bootstrap_left_catalog_in_sync_and_audited():
    assert catalog_drift() == []
    synced = AuditEvent.objects.filter(action="rbac.permission_catalog.synced")
    seeded = AuditEvent.objects.filter(action="rbac.system_roles.seeded")
    assert synced.exists() and seeded.exists()
    event = synced.first()
    assert event is not None and event.actor_type == "system"
    declared = Permission.objects.filter(deprecated_at__isnull=True).count()
    assert event.metadata["declared"] == declared


def test_create_platform_admin_refuses_while_the_catalog_drifts(monkeypatch):
    from apps.rbac import registry, seeding

    real = registry.declared_permissions()
    extra = registry.PermissionSpec(
        code="identity.future.thing",
        module_code="identity",
        description="not yet synced",
        is_sensitive=False,
        requires_mfa=False,
        requires_step_up=False,
    )
    monkeypatch.setattr(seeding, "declared_permissions", lambda: {**real, extra.code: extra})
    with pytest.raises(CommandError, match="not synchronized"):
        call_command("create_platform_admin", "--email", "drift@example.com", stdout=StringIO())
    assert not User.objects.filter(email="drift@example.com").exists()


def test_compose_bootstrap_seeds_as_owner_and_runtime_services_get_no_owner_url():
    compose = yaml.safe_load((BACKEND.parent / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    script = services["migrate"]["entrypoint"][-1]
    assert script.startswith('export DATABASE_URL="$$DATABASE_MIGRATION_URL" && ')
    assert script.index("migrate --noinput") < script.index("seed_roles")
    for name in ("api", "worker", "beat", "web"):
        env = services[name].get("environment", {}) or {}
        assert "DATABASE_MIGRATION_URL" not in env, name
        assert "seed_roles" not in str(services[name].get("command", "")), name


# --------------------------------------------------------------------------- real bootstrap
def test_owner_bootstrap_is_repeatable_idempotent_and_runtime_role_is_refused(owner_dsn):
    """Real commands on a throwaway database: owner bootstrap twice, deprecation, refusal as
    erp_app, and ``create_platform_admin`` working as erp_app with a read-only catalogue."""
    name = f"erp_catalog_{uuid.uuid4().hex[:8]}"
    host, port = owner_dsn["host"], owner_dsn["port"]
    with psycopg.connect(**owner_dsn, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}" TEMPLATE template1')
    owner_url = f"postgres://{owner_dsn['user']}:{owner_dsn['password']}@{host}:{port}/{name}"
    app_user = connection.settings_dict["USER"]
    app_url = f"postgres://{app_user}:{connection.settings_dict['PASSWORD']}@{host}:{port}/{name}"
    base_env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings.test"}

    def manage(*args: str, as_url: str = owner_url, ok: bool = True) -> str:
        result = subprocess.run(  # noqa: S603 - fixed interpreter and arguments
            [sys.executable, "manage.py", *args],
            cwd=BACKEND,
            # config.settings.test connects with DATABASE_MIGRATION_URL.
            env={**base_env, "DATABASE_MIGRATION_URL": as_url, "DATABASE_URL": app_url},
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        output = result.stdout + result.stderr
        assert (result.returncode == 0) is ok, output
        return output

    try:
        manage("migrate", "--noinput")
        first = manage("seed_roles")
        assert "permissions: 86 created" in first and "system roles: 22 seeded (22 created" in first
        second = manage("seed_roles")
        assert "permissions: 0 created, 0 updated, 0 deprecated" in second
        assert "(0 created, 0 permissions added, 0 removed)" in second

        # Phase 5 M2: presets sync idempotently, only as the owner, and are immutable.
        assert "presets: 12 declared, 12 created, 0 deprecated" in manage("sync_presets")
        assert "presets: 12 declared, 0 created, 0 deprecated" in manage("sync_presets")
        assert "owner role" in manage("sync_presets", as_url=app_url, ok=False)
        with psycopg.connect(owner_url, autocommit=True) as conn:
            conn.execute(
                "UPDATE customization_preset SET checksum = 'x' WHERE code = 'school.general.v1'"
            )
        assert "immutable" in manage("sync_presets", ok=False)

        manage(
            "shell",
            "-c",
            "from apps.rbac.models import Permission; Permission.objects.create("
            "code='identity.legacy.thing', module_code='identity', description='old')",
        )
        assert "1 deprecated" in manage("sync_permissions")
        assert "0 created, 0 updated, 0 deprecated" in manage("sync_permissions")

        refused = manage("seed_roles", as_url=app_url, ok=False)
        assert "must run as the database owner role" in refused
        denied = manage(
            "shell",
            "-c",
            "from apps.rbac.models import Permission; "
            "Permission.objects.filter(code='identity.user.view').update(requires_mfa=False)",
            as_url=app_url,
            ok=False,
        )
        assert "permission denied for table rbac_permission" in denied

        created = manage("create_platform_admin", "--email", "boot@example.test", as_url=app_url)
        assert "Super Admin created" in created

        with psycopg.connect(owner_url) as conn:
            counts = conn.execute(
                "SELECT action, count(*) FROM audit_auditevent WHERE action LIKE 'rbac.%%' "
                "GROUP BY action ORDER BY action"
            ).fetchall()
            mfa = conn.execute(
                "SELECT requires_mfa FROM rbac_permission WHERE code = 'identity.user.view'"
            ).fetchone()
        # 2 x seed_roles (sync + seed each) + 2 x sync_permissions; refused runs write nothing.
        assert dict(counts)["rbac.permission_catalog.synced"] == 4
        assert dict(counts)["rbac.system_roles.seeded"] == 2
        assert mfa == (True,)
    finally:
        with psycopg.connect(**owner_dsn, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def test_catalog_drift_reports_outdated_permissions_and_roles(monkeypatch):
    from dataclasses import replace

    from apps.rbac import registry, seeding

    real = registry.declared_permissions()
    changed = replace(real["identity.user.view"], requires_mfa=False)
    monkeypatch.setattr(seeding, "declared_permissions", lambda: {**real, changed.code: changed})
    rows = seeding._role_rows()
    ghost = {"code": "ghost_role", "permissions": [], "planned": []}
    first_kind, first = rows[0]
    narrowed = {**first, "permissions": ["identity.user.view"], "planned": []}
    monkeypatch.setattr(
        seeding, "_role_rows", lambda: [(first_kind, narrowed), *rows[1:], (first_kind, ghost)]
    )
    drift = seeding.catalog_drift()
    assert "permission identity.user.view out of date" in drift
    assert "system role ghost_role missing" in drift
    assert f"system role {first['code']} permissions out of date" in drift
