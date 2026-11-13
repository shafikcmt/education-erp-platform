"""Pure host policy (Phase 3 plan §10.1 steps 2-4; ADR-041). No I/O.

A request host is the platform, a tenant *candidate* (it has exactly the shape
``<slug>.<TENANT_BASE_DOMAIN>``; whether such a tenant exists is decided later by F1), or
rejected. Rejected hosts and unknown tenants receive the same uniform 404, and while tenant
hosts are disabled nothing is ever looked up (D1).

The tenant is chosen from the host alone: headers such as ``X-Tenant`` and ids in bodies or
query strings never take part.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum

from apps.core.net import normalize_host
from apps.tenancy.rules import InvalidSlug, is_valid_domain, validate_slug


class HostKind(StrEnum):
    PLATFORM = "platform"
    TENANT = "tenant"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class HostDecision:
    kind: HostKind
    host: str
    slug: str = ""
    reason: str = ""


def classify_host(
    raw_host: str,
    *,
    platform_hosts: Collection[str],
    tenant_base_domain: str,
    tenant_hosts_enabled: bool,
) -> HostDecision:
    host = normalize_host(raw_host)
    if host and host in platform_hosts:
        return HostDecision(HostKind.PLATFORM, host)
    if not tenant_hosts_enabled:
        return HostDecision(HostKind.REJECTED, host, reason="tenant_hosts_disabled")
    suffix = "." + tenant_base_domain
    # ``is_valid_domain`` refuses IP literals, non-ASCII, underscores, empty labels and a
    # trailing dot; the label must then be exactly one valid, non-reserved slug.
    if not tenant_base_domain or not is_valid_domain(host) or not host.endswith(suffix):
        return HostDecision(HostKind.REJECTED, host, reason="not_a_tenant_host")
    label = host[: -len(suffix)]
    try:
        validate_slug(label)
    except InvalidSlug:
        return HostDecision(HostKind.REJECTED, host, reason="not_a_tenant_host")
    return HostDecision(HostKind.TENANT, host, slug=label)
