"""Static checks against unsafe tenant-context and role operations (plan §5.3; ADR-009 §4).

Runtime code, migrations, settings and infrastructure scripts must never:

* change role (``SET ROLE`` / ``RESET ROLE``) or set session-level state (``SET SESSION``);
* set the tenant at session level (``SET app.tenant_id`` / ``SET SESSION app.…``);
* call ``set_config('app.tenant_id', …, false)`` (session scope).

Test modules are excluded: they contain these strings as *negative* tests (for example the
check that ``erp_app`` cannot ``SET ROLE erp_owner``).
"""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent

SCAN_ROOTS = [BACKEND / "apps", BACKEND / "config", REPO / "infra"]
SUFFIXES = {".py", ".sql", ".sh", ".conf"}

FORBIDDEN = {
    "SET ROLE": re.compile(r"\bSET\s+ROLE\b", re.IGNORECASE),
    "RESET ROLE": re.compile(r"\bRESET\s+ROLE\b", re.IGNORECASE),
    "SET SESSION": re.compile(r"\bSET\s+SESSION\b", re.IGNORECASE),
    "SET app.*": re.compile(r"\bSET\s+(LOCAL\s+)?app\.", re.IGNORECASE),
    "set_config(..., false)": re.compile(
        r"set_config\s*\(\s*['\"]app\.[^'\"]+['\"]\s*,[^)]*,\s*(false|0|False)\s*\)", re.IGNORECASE
    ),
}


def _is_test_file(path: Path) -> bool:
    return "tests" in path.relative_to(REPO).parts or path.name.startswith("test_")


def _sources():
    for root in SCAN_ROOTS:
        for path in root.rglob("*"):
            if path.suffix in SUFFIXES and path.is_file() and not _is_test_file(path):
                if ".venv" in path.parts or "__pycache__" in path.parts:
                    continue
                yield path


def scan(text: str) -> list[str]:
    return [name for name, pattern in FORBIDDEN.items() if pattern.search(text)]


def test_no_unsafe_role_or_session_operations_in_runtime_code():
    findings = []
    for path in _sources():
        for name in scan(path.read_text(encoding="utf-8", errors="replace")):
            findings.append(f"{path.relative_to(REPO)}: {name}")
    assert findings == []


def test_scanner_covers_application_infrastructure_and_migrations():
    scanned = {p.relative_to(REPO).as_posix() for p in _sources()}
    assert "backend/apps/core/tenancy/transaction.py" in scanned
    assert "backend/apps/core/db_operations.py" in scanned
    assert "infra/docker/postgres/init/01-roles.sh" in scanned
    assert any(p.startswith("backend/apps/core/migrations/") for p in scanned)


def test_scanner_detects_each_forbidden_pattern():
    samples = {
        "SET ROLE": "cursor.execute('SET ROLE erp_platform')",
        "RESET ROLE": "RESET ROLE;",
        "SET SESSION": "SET SESSION AUTHORIZATION erp_owner",
        "SET app.*": "SET app.tenant_id = 'x'",
        "set_config(..., false)": "SELECT set_config('app.tenant_id', %s, false)",
    }
    for name, sample in samples.items():
        assert name in scan(sample), name
    assert scan("SELECT set_config('app.tenant_id', %s, true)") == []
    assert scan("SET search_path = pg_catalog, pg_temp") == []
