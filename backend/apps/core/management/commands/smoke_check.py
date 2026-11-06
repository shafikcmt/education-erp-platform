"""End-to-end infrastructure smoke check against the running stack.

    docker compose exec api python manage.py smoke_check

Verifies (and exits non-zero on any failure):
  * database: connected as a non-superuser, NOBYPASSRLS role with no DDL rights (ADR-009),
    and the required extensions are installed;
  * cache: Redis set/get/delete;
  * storage: S3 write -> read -> delete round-trip in the configured bucket;
  * celery: `core.ping` round-trip through broker, worker and result backend.
"""

import json
from collections.abc import Callable
from typing import Any

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.core.ids import new_id

REQUIRED_EXTENSIONS = {"vector", "pg_trgm", "btree_gist", "citext"}


def check_database_role() -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_user, r.rolsuper, r.rolbypassrls, "
            "has_schema_privilege(current_user, 'public', 'CREATE'), "
            "has_database_privilege(current_user, current_database(), 'TEMPORARY'), "
            "has_database_privilege(current_user, current_database(), 'CREATE') "
            "FROM pg_roles r WHERE r.rolname = current_user"
        )
        row = cursor.fetchone()
        cursor.execute("SELECT extname FROM pg_extension")
        extensions = {r[0] for r in cursor.fetchall()}
    if row is None:
        raise CommandError("could not read the current database role")
    user, is_super, bypass_rls, can_create, can_temp, can_create_schema = row
    missing = REQUIRED_EXTENSIONS - extensions
    if is_super or bypass_rls or can_create or can_temp or can_create_schema or missing:
        raise CommandError(
            f"database role check failed: user={user} superuser={is_super} "
            f"bypassrls={bypass_rls} create_in_public={can_create} temp={can_temp} "
            f"create_schema={can_create_schema} missing_ext={sorted(missing)}"
        )
    return {
        "user": user,
        "superuser": is_super,
        "bypassrls": bypass_rls,
        "temporary": can_temp,
        "create_schema": can_create_schema,
    }


def check_cache_roundtrip() -> dict[str, Any]:
    key = f"smoke:{new_id()}"
    cache.set(key, "ok", timeout=30)
    value = cache.get(key)
    cache.delete(key)
    if value != "ok":
        raise CommandError("cache round-trip failed")
    return {"roundtrip": True}


def check_storage_roundtrip() -> dict[str, Any]:
    name = default_storage.save(f"_smoke/{new_id()}.txt", ContentFile(b"smoke-check"))
    try:
        with default_storage.open(name, "rb") as handle:
            content = handle.read()
    finally:
        default_storage.delete(name)
    if content != b"smoke-check":
        raise CommandError("storage round-trip returned unexpected content")
    return {"roundtrip": True, "exists_after_delete": default_storage.exists(name)}


def check_celery_roundtrip(timeout: float = 30.0) -> dict[str, Any]:
    from apps.core.tasks import ping

    result = ping.apply_async(queue="default").get(timeout=timeout)
    if result != "pong":
        raise CommandError(f"celery round-trip returned {result!r}")
    return {"result": result}


CHECKS: dict[str, Callable[[], dict[str, Any]]] = {
    "database": check_database_role,
    "cache": check_cache_roundtrip,
    "storage": check_storage_roundtrip,
    "celery": check_celery_roundtrip,
}


class Command(BaseCommand):
    help = "Verify database role, cache, object storage and Celery against the running stack."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--skip", action="append", default=[], choices=sorted(CHECKS))

    def handle(self, *args: Any, **options: Any) -> None:
        report: dict[str, Any] = {}
        failed = False
        for name, check in CHECKS.items():
            if name in options["skip"]:
                report[name] = {"skipped": True}
                continue
            try:
                report[name] = {"ok": True, **check()}
            except Exception as exc:  # report every failure, then fail once
                failed = True
                report[name] = {"ok": False, "error": str(exc)}
        self.stdout.write(json.dumps(report, indent=2, default=str))
        if failed:
            raise CommandError("smoke check failed")
