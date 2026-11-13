"""Request path for hosts and tenants (Phase 3 plan §8.2-§8.4, §10.1; ADR-041, ADR-042).

Order (see ``MIDDLEWARE``)::

    RequestID -> Security -> HostPolicy -> Session -> Common -> CSRF -> Auth -> SessionSecurity
      -> TenantResolution -> TenantTransaction -> ApiNoStore -> XFrameOptions

* :class:`HostPolicyMiddleware` is pure: it classifies the host before any session or database
  work. Rejected hosts get the uniform 404; while tenant hosts are disabled nothing is looked
  up at all (D1).
* :class:`TenantResolutionMiddleware` binds the session to its host, resolves a tenant host
  with F1 (one indexed lookup, never cached) and sets ``request.tenant`` and
  ``request.scope_target``.
* :class:`TenantTransactionMiddleware` runs every tenant-host request in ONE tenant
  transaction, rolls it back for error responses, refuses streaming bodies and enforces the
  host class of the view and the membership gate. Platform hosts stay in autocommit exactly
  as in Phase 2.
"""

from __future__ import annotations

import itertools
import time
from collections.abc import Callable
from typing import Any

import structlog
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from django.http import HttpRequest, HttpResponse

from apps.audit.services import record as audit
from apps.core import hosts
from apps.core.exceptions import problem_response, uniform_not_found
from apps.core.net import normalize_host
from apps.core.tenancy import TenantContext, tenant_atomic
from apps.core.tenancy.platform import platform_scope
from apps.rbac.engine import PLATFORM, ScopeTarget
from apps.tenancy import access
from apps.tenancy.hosts import HostKind, classify_host
from apps.tenancy.selectors.platform import resolve_host

logger = structlog.get_logger("erp.tenancy")

HEALTH_PATHS = frozenset({"/healthz", "/readyz"})
_REJECTION_LOG_SAMPLE = 20  # log one rejected host in N (they can be attacker-driven)
_rejections = itertools.count()

GetResponse = Callable[[HttpRequest], HttpResponse]


def _reject(request: HttpRequest, reason: str) -> HttpResponse:
    if next(_rejections) % _REJECTION_LOG_SAMPLE == 0:
        logger.info("tenancy.host.rejected", reason=reason, sampled=_REJECTION_LOG_SAMPLE)
    return uniform_not_found(request)


class HostPolicyMiddleware:
    """Steps 0-4 of the decision table. No I/O."""

    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.tenant = None  # type: ignore[attr-defined]
        request.tenant_host = ""  # type: ignore[attr-defined]
        if request.path in HEALTH_PATHS:
            # Probes are host-independent and never get a session or a tenant.
            request.host_kind = hosts.PLATFORM  # type: ignore[attr-defined]
            return self.get_response(request)
        decision = classify_host(
            request.get_host(),  # raises DisallowedHost -> 400, as before
            platform_hosts=settings.PLATFORM_HOSTS,
            tenant_base_domain=settings.TENANT_BASE_DOMAIN,
            tenant_hosts_enabled=settings.TENANT_HOSTS_ENABLED,
        )
        if decision.kind is HostKind.REJECTED:
            return _reject(request, decision.reason)
        request.host_kind = decision.kind.value  # type: ignore[attr-defined]
        if decision.kind is HostKind.TENANT:
            request.tenant_host = decision.host  # type: ignore[attr-defined]
            request.tenant_slug = decision.slug  # type: ignore[attr-defined]
        return self.get_response(request)


class TenantResolutionMiddleware:
    """Steps 5-6: session-host binding, F1 and the authorization scope."""

    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.scope_target = PLATFORM  # type: ignore[attr-defined]
        kind = getattr(request, "host_kind", hosts.PLATFORM)
        if request.path not in HEALTH_PATHS:
            self._bind_session_to_host(request, kind)
        if kind != hosts.TENANT:
            return self.get_response(request)
        host: str = request.tenant_host  # type: ignore[attr-defined]
        with platform_scope(operation="P1", actor=None, reason="resolve request host"):
            resolution = resolve_host(host)
        if resolution is None:  # unknown, unverified, provisioning or deleted: all alike
            return _reject(request, "unknown_tenant")
        tenant = TenantContext(
            id=resolution.tenant_id,
            slug=getattr(request, "tenant_slug", ""),
            status=resolution.status,
        )
        request.tenant = tenant  # type: ignore[attr-defined]
        request.scope_target = ScopeTarget(tenant_id=tenant.id)  # type: ignore[attr-defined]
        return self.get_response(request)

    @staticmethod
    def _bind_session_to_host(request: HttpRequest, kind: str) -> None:
        """A session is valid only on the host it was created on (plan §8.2). Cookies are
        host-only, so a mismatch means a replayed or planted cookie: the request continues
        as anonymous. The session itself is NOT revoked, so replaying a cookie elsewhere
        can't sign the real user out."""
        record = getattr(request, "session_record", None)
        if record is None or not request.user.is_authenticated:
            return
        if normalize_host(record.host) == normalize_host(request.get_host()):
            return
        audit(
            "tenancy.isolation.blocked",
            outcome="denied",
            actor_user_id=request.user.pk,
            request=request,
            metadata={"reason": "session_host_mismatch", "host_kind": kind},
        )
        # A fresh, empty session: the middleware then drops the misplaced cookie on this
        # host only and leaves the stored session untouched.
        request.session = type(request.session)()
        request.user = AnonymousUser()
        request.session_record = None  # type: ignore[attr-defined]


class TenantTransactionMiddleware:
    """One tenant transaction per tenant-host request; host classes for every request."""

    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        tenant: TenantContext | None = getattr(request, "tenant", None)
        if tenant is None:
            return self.get_response(request)
        started = time.perf_counter()
        status_code = 500
        try:
            with tenant_atomic(tenant, lock_timeout=settings.TENANT_REQUEST_LOCK_TIMEOUT):
                response = self.get_response(request)
                if getattr(response, "streaming", False):
                    # The body would be produced after the transaction (and the tenant
                    # context) has ended. Tenant exports are asynchronous jobs instead.
                    logger.error("tenancy.streaming_response_refused", path=request.path)
                    response = problem_response(
                        request, 500, "internal_error", "Internal server error"
                    )
                status_code = response.status_code
                if status_code >= 400:
                    # A request that failed must leave no data and no "success" audit
                    # events behind; denial evidence was written durably (plan §8.3).
                    transaction.set_rollback(True)
            return response
        finally:
            tx_ms = round((time.perf_counter() - started) * 1000, 2)
            log = logger.warning if tx_ms > settings.TENANT_TX_WARN_MS else logger.info
            log(
                "tenant_request",
                tenant_id=str(tenant.id),
                tx_ms=tx_ms,
                status=status_code,
                slow=tx_ms > settings.TENANT_TX_WARN_MS,
            )

    def process_view(
        self, request: HttpRequest, view_func: Any, view_args: Any, view_kwargs: Any
    ) -> HttpResponse | None:
        kind = getattr(request, "host_kind", hosts.PLATFORM)
        if kind not in hosts.host_classes_of(view_func):
            return uniform_not_found(request)
        tenant: TenantContext | None = getattr(request, "tenant", None)
        if tenant is None or getattr(hosts.view_class(view_func), "tenant_auth_flow", False):
            return None
        return access.check_request(request, tenant)
