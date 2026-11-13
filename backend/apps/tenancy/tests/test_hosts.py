"""Pure host policy: decision-table steps 2-4 (Phase 3 M3; plan §10.1, ADR-041)."""

from __future__ import annotations

import pytest

from apps.core.net import normalize_host
from apps.tenancy.hosts import HostKind, classify_host

CONFIG = {
    "platform_hosts": ["admin.erp.test", "localhost", "api"],
    "tenant_base_domain": "erp.test",
    "tenant_hosts_enabled": True,
}


def classify(host: str, **overrides):
    return classify_host(host, **{**CONFIG, **overrides})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Acme.ERP.test", "acme.erp.test"),
        ("acme.erp.test:8443", "acme.erp.test"),
        (" localhost:8080 ", "localhost"),
        ("[::1]:8000", "[::1]"),
        ("[::1]", "[::1]"),
        ("[::1", ""),
        ("a:b:c", ""),
        ("acme.erp.test.", "acme.erp.test."),  # trailing dot is a different cookie host
        ("", ""),
    ],
)
def test_normalize_host(raw, expected):
    assert normalize_host(raw) == expected


@pytest.mark.parametrize("host", ["localhost", "LOCALHOST:8080", "api", "admin.erp.test"])
def test_platform_hosts_match_exactly_after_normalisation(host):
    decision = classify(host)
    assert decision.kind is HostKind.PLATFORM
    # Platform hosts never depend on the tenant switch.
    assert classify(host, tenant_hosts_enabled=False).kind is HostKind.PLATFORM


@pytest.mark.parametrize("host", ["acme.erp.test", "ACME.erp.test:443", "madrasa-2026.erp.test"])
def test_tenant_candidates(host):
    decision = classify(host)
    assert decision.kind is HostKind.TENANT
    assert decision.host == host.lower().split(":")[0]
    assert decision.slug == decision.host.removesuffix(".erp.test")


@pytest.mark.parametrize(
    "host",
    [
        "erp.test",  # the bare base domain
        "a.b.erp.test",  # more than one extra label
        "acme.erp.test.",  # trailing dot
        "acme.erp.test.evil.example",  # base domain not at the end
        "acmeerp.test",  # suffix without the dot boundary
        "evil-erp.test",
        "ab.erp.test",  # slug too short
        "1abc.erp.test",  # slug must start with a letter
        "a--b.erp.test",
        "ac_me.erp.test",
        "www.erp.test",  # reserved slug that is not a platform host
        "api.erp.test",
        "xn--acm-dma.erp.test",  # punycode: '--' is refused
        "acmé.erp.test",  # non-ASCII
        "127.0.0.1",
        "10.0.0.5:8000",
        "[::1]:8000",
        "localhost.",  # platform hosts match exactly
        "admin.erp.test.",
        "sub.localhost",
        "",
        "a:b:c",
        "x" * 300 + ".erp.test",
    ],
)
def test_everything_else_is_rejected(host):
    decision = classify(host)
    assert decision.kind is HostKind.REJECTED
    assert decision.reason == "not_a_tenant_host"


@pytest.mark.parametrize("host", ["acme.erp.test", "erp.test", "127.0.0.1", "", "www.erp.test"])
def test_disabled_mode_rejects_every_non_platform_host_with_one_reason(host):
    decision = classify(host, tenant_hosts_enabled=False)
    assert (decision.kind, decision.reason) == (HostKind.REJECTED, "tenant_hosts_disabled")


def test_enabled_without_a_base_domain_serves_no_tenant():
    assert classify("acme.erp.test", tenant_base_domain="").kind is HostKind.REJECTED
