#!/usr/bin/env python3
"""Fail if database owner/superuser credentials reach runtime containers (review H3).

Usage:  docker compose config --format json | python3 infra/scripts/check_runtime_secrets.py

Rules (stdlib only, so it runs anywhere CI runs):
* ``DATABASE_MIGRATION_URL`` only in ``migrate``; bootstrap passwords only in ``postgres``;
* no other service may carry the owner/superuser password under ANY variable name;
* no service other than ``migrate`` may use the owner or superuser role in ``DATABASE_URL``.
"""

from __future__ import annotations

import json
import sys
from typing import Any
from urllib.parse import urlsplit

ALLOWED: dict[str, set[str]] = {
    "DATABASE_MIGRATION_URL": {"migrate"},
    "ERP_OWNER_PASSWORD": {"postgres"},
    "POSTGRES_PASSWORD": {"postgres"},
    "ERP_APP_PASSWORD": {"postgres"},
}
PRIVILEGED_USERS = {"erp_owner", "postgres"}


def problems(config: dict[str, Any]) -> list[str]:
    services: dict[str, Any] = config.get("services", {})
    envs = {name: {k: str(v or "") for k, v in (svc.get("environment") or {}).items()}
            for name, svc in services.items()}
    found: list[str] = []
    for name, svc in services.items():
        if svc.get("env_file"):
            found.append(f"{name}: env_file is not allowed (use an explicit allow-list)")
    for var, owners in ALLOWED.items():
        for name, env in envs.items():
            if env.get(var) and name not in owners:
                found.append(f"{name}: must not receive {var}")
    secrets = {v for k in ("ERP_OWNER_PASSWORD", "POSTGRES_PASSWORD")
               for v in [envs.get("postgres", {}).get(k, "")] if len(v) >= 6}
    for name, env in envs.items():
        if name in {"postgres", "migrate"}:
            continue
        for key, value in env.items():
            if any(secret in value for secret in secrets):
                found.append(f"{name}: {key} contains an owner/superuser password")
    for name, env in envs.items():
        url = env.get("DATABASE_URL", "")
        if url and name != "migrate" and (urlsplit(url).username or "") in PRIVILEGED_USERS:
            found.append(f"{name}: DATABASE_URL uses a privileged role")
    return found


def main() -> int:
    found = problems(json.load(sys.stdin))
    for line in found:
        print(f"SECRET ISOLATION VIOLATION: {line}")
    if not found:
        print("runtime secret isolation: OK")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
