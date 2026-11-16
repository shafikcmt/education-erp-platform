"""Probe views for the tenant request path (tests only; Phase 3 M3).

They expose what the middleware decided and let a test write a tenant row and then fail,
so rollback, durable audit, ``on_commit`` and leak behaviour can be observed end to end.
"""

from __future__ import annotations

from typing import Any

from django.db import connection, transaction
from django.http import StreamingHttpResponse
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.hosts import PLATFORM_AND_TENANT, TENANT_ONLY
from apps.core.tenancy import current_tenant
from apps.rbac.permissions import HasPermission
from tests.isolation_app.models import ProbeRecord

ON_COMMIT_LOG: list[str] = []


def _db_state() -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_setting('app.tenant_id', true), pg_backend_pid(), "
            "current_setting('lock_timeout')"
        )
        setting, pid, lock_timeout = cursor.fetchone()
        cursor.execute("SELECT tenant_id::text FROM isolation_probe_record")
        raw = sorted({row[0] for row in cursor.fetchall()})
    return {"setting": setting or "", "pid": pid, "lock_timeout": lock_timeout, "raw": raw}


class _Open(APIView):
    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]
    host_classes = PLATFORM_AND_TENANT


class WhoAmI(_Open):
    def get(self, request: Request) -> Response:
        tenant = getattr(request._request, "tenant", None)
        ctx = current_tenant()
        return Response(
            {
                "host_kind": request._request.host_kind,  # type: ignore[attr-defined]
                "tenant": str(tenant.id) if tenant else None,
                "status": tenant.status if tenant else None,
                "context": str(ctx.id) if ctx else None,
                "scope": request._request.scope_target.cache_key(),  # type: ignore[attr-defined]
                **_db_state(),
            }
        )


class Records(_Open):
    host_classes = TENANT_ONLY

    def get(self, request: Request) -> Response:
        names = sorted(ProbeRecord.objects.values_list("name", flat=True))
        return Response({"names": names, **_db_state()})

    def post(self, request: Request) -> Any:
        name = str(request.data.get("name", "probe"))
        mode = request.query_params.get("then", "")
        ProbeRecord.objects.create(name=name)
        transaction.on_commit(lambda: ON_COMMIT_LOG.append(name))
        if mode == "savepoint":
            try:
                with transaction.atomic():
                    ProbeRecord.objects.create(name=f"{name}-inner")
                    raise ValueError("inner failure")
            except ValueError:
                pass
        if mode == "403":
            raise PermissionDenied()
        if mode == "bypass":
            # A query on another connection that never applied this tenant: the guard
            # refuses it before it reaches PostgreSQL.
            ProbeRecord.objects.using("isolation_secondary").count()
        if mode == "raise":
            raise RuntimeError("probe failure")
        if mode == "stream":
            return StreamingHttpResponse(iter([b"chunk"]))
        return Response({"created": name}, status=201)


class Protected(APIView):
    """Needs a platform permission: nobody holds it on a tenant host (ADR-031/037)."""

    permission_classes = [HasPermission("identity.user.view")]
    host_classes = PLATFORM_AND_TENANT

    def get(self, request: Request) -> Response:
        return Response({"ok": True})


class TenantProtected(APIView):
    """Needs a tenant permission in the request's (tenant-level) scope."""

    permission_classes = [HasPermission("tenancy.member.view")]
    host_classes = TENANT_ONLY

    def get(self, request: Request) -> Response:
        return Response({"ok": True})


class PlatformOnly(_Open):
    host_classes = frozenset({"platform"})

    def get(self, request: Request) -> Response:
        return Response({"ok": True})


class TenantOnly(_Open):
    host_classes = TENANT_ONLY

    def get(self, request: Request) -> Response:
        return Response({"ok": True})
