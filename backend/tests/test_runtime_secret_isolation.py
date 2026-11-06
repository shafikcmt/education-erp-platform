"""Review H3: the compose checker rejects owner/superuser credentials in runtime services."""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "check_runtime_secrets", ROOT / "infra/scripts/check_runtime_secrets.py"
)
assert SPEC and SPEC.loader
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)

GOOD = {
    "services": {
        "postgres": {
            "environment": {
                "POSTGRES_PASSWORD": "superpw123",
                "ERP_OWNER_PASSWORD": "ownerpw123",
                "ERP_APP_PASSWORD": "apppw123",
            }
        },
        "migrate": {
            "environment": {
                "DATABASE_MIGRATION_URL": "postgres://erp_owner:ownerpw123@postgres/erp",
                "DATABASE_URL": "postgres://erp_app:apppw123@postgres/erp",
            }
        },
        "api": {"environment": {"DATABASE_URL": "postgres://erp_app:apppw123@postgres/erp"}},
    }
}


def _with(service, env):
    config = json.loads(json.dumps(GOOD))
    config["services"].setdefault(service, {}).setdefault("environment", {}).update(env)
    return config


def test_good_config_passes():
    assert checker.problems(GOOD) == []


@pytest.mark.parametrize(
    ("service", "env", "message"),
    [
        ("api", {"DATABASE_MIGRATION_URL": "postgres://erp_owner:ownerpw123@x/erp"}, "must not"),
        ("worker", {"POSTGRES_PASSWORD": "superpw123"}, "must not"),
        ("web", {"SNEAKY": "ownerpw123"}, "contains an owner"),
        ("beat", {"DATABASE_URL": "postgres://erp_owner:z@x/erp"}, "privileged role"),
        ("api", {"DATABASE_URL": "postgres://postgres:z@x/erp"}, "privileged role"),
    ],
)
def test_violations_are_reported(service, env, message):
    found = checker.problems(_with(service, env))
    assert any(message in line and line.startswith(service) for line in found), found


def test_env_file_is_rejected():
    config = json.loads(json.dumps(GOOD))
    config["services"]["api"]["env_file"] = [".env"]
    assert any("env_file" in line for line in checker.problems(config))


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not available")
def test_repository_compose_file_passes():
    if not (ROOT / ".env").exists():
        pytest.skip("no .env (copy .env.example)")
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("docker compose unavailable")
    assert checker.problems(json.loads(result.stdout)) == []
