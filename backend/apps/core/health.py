"""Liveness / readiness probes and the public system-health API endpoint.

* ``/healthz`` — liveness: the process can serve HTTP. No dependency checks.
* ``/readyz``  — readiness: PostgreSQL, Redis cache and object storage are reachable.
  Returns 503 Problem Details if any check fails. Only check names and ``ok``/``fail`` are
  exposed (no hostnames or error text) — Nginx restricts it to internal callers in production.
* ``GET /api/v1/system/health/`` — documented in OpenAPI; overall status + version only.
"""

from collections.abc import Callable

import structlog
from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.db import connection
from django.http import HttpRequest, JsonResponse
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import PROBLEM_CONTENT_TYPE, problem
from apps.core.ids import new_id
from apps.core.middleware import get_request_id

logger = structlog.get_logger("erp.health")


def check_database() -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        row = cursor.fetchone()
    return row is not None and row[0] == 1


def check_cache() -> bool:
    key = f"health:{new_id()}"
    cache.set(key, "1", timeout=10)
    ok = bool(cache.get(key) == "1")
    cache.delete(key)
    return ok


def check_storage() -> bool:
    """Verify the configured bucket is reachable (S3 HeadBucket) without writing data."""
    connection_obj = getattr(default_storage, "connection", None)
    if connection_obj is None:  # non-S3 backend (tests use in-memory storage)
        return True
    connection_obj.meta.client.head_bucket(Bucket=default_storage.bucket_name)  # type: ignore[attr-defined]
    return True


READINESS_CHECKS: dict[str, Callable[[], bool]] = {
    "database": check_database,
    "cache": check_cache,
    "storage": check_storage,
}


def run_readiness_checks() -> dict[str, str]:
    results: dict[str, str] = {}
    for name, check in READINESS_CHECKS.items():
        try:
            results[name] = "ok" if check() else "fail"
        except Exception:  # any failure means not ready; details go to logs only
            logger.warning("readiness_check_failed", check=name, exc_info=True)
            results[name] = "fail"
    return results


def healthz(request: HttpRequest) -> JsonResponse:
    """Liveness probe."""
    return JsonResponse({"status": "ok"})


def readyz(request: HttpRequest) -> JsonResponse:
    """Readiness probe."""
    checks = run_readiness_checks()
    if all(value == "ok" for value in checks.values()):
        return JsonResponse({"status": "ok", "checks": checks})
    body = problem(
        status_code=503,
        code="service_unavailable",
        title="Service unavailable",
        detail="One or more dependencies are not ready.",
        request_id=get_request_id(request),
        extra={"checks": checks},
    )
    return JsonResponse(body, status=503, content_type=PROBLEM_CONTENT_TYPE)


class SystemHealthSerializer(serializers.Serializer[dict[str, str]]):
    status = serializers.ChoiceField(choices=["ok", "degraded"])
    version = serializers.CharField()
    environment = serializers.CharField()


class SystemHealthView(APIView):
    """Public, minimal health summary used by the frontend system page."""

    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(
        operation_id="system_health",
        summary="System health summary",
        tags=["system"],
        responses={200: SystemHealthSerializer},
    )
    def get(self, request: Request) -> Response:
        checks = run_readiness_checks()
        payload = {
            "status": "ok" if all(v == "ok" for v in checks.values()) else "degraded",
            "version": settings.APP_VERSION,
            "environment": settings.APP_ENVIRONMENT,
        }
        return Response(SystemHealthSerializer(payload).data)
