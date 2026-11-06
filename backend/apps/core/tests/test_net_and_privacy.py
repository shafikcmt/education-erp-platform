"""IP handling (ADR-036), user-agent summaries, Sentry scrubbing and API cache headers."""

import pytest
from django.test import RequestFactory, override_settings

from apps.core.ip_privacy import open_ip, seal_ip
from apps.core.net import client_ip, ip_prefix, mask_ip, normalize_ip, user_agent_summary
from apps.core.observability import scrub_event


@pytest.mark.parametrize(
    ("value", "normal", "prefix", "masked"),
    [
        ("203.0.113.9", "203.0.113.9", "203.0.113.0/24", "203.0.113.•"),
        ("::ffff:203.0.113.9", "203.0.113.9", "203.0.113.0/24", "203.0.113.•"),
        (
            "2001:db8:85a3::8a2e:370:7334",
            "2001:db8:85a3::8a2e:370:7334",
            "2001:db8:85a3::/48",
            "2001:db8:85a3::•",
        ),
        ("not-an-ip", "", "", ""),
    ],
)
def test_ip_normalisation_prefix_and_mask(value, normal, prefix, masked):
    assert normalize_ip(value) == normal
    assert ip_prefix(value) == prefix
    assert mask_ip(value) == masked


def test_client_ip_uses_only_the_trusted_proxy_header():
    request = RequestFactory().get("/", REMOTE_ADDR="10.0.0.2", HTTP_X_REAL_IP="203.0.113.5")
    assert client_ip(request) == "10.0.0.2"  # header not trusted by default
    with override_settings(CLIENT_IP_HEADER="HTTP_X_REAL_IP"):
        assert client_ip(request) == "203.0.113.5"
        bad = RequestFactory().get("/", REMOTE_ADDR="10.0.0.2", HTTP_X_REAL_IP="evil")
        assert client_ip(bad) == "10.0.0.2"


def test_sealed_ip_is_encrypted_and_reversible():
    sealed = seal_ip("203.0.113.9")
    assert sealed.ip_encrypted and b"203.0.113.9" not in sealed.ip_encrypted
    assert sealed.ip_prefix == "203.0.113.0/24"
    assert open_ip(sealed.ip_encrypted) == "203.0.113.9"
    assert seal_ip("").ip_encrypted is None


@pytest.mark.parametrize(
    ("ua", "summary"),
    [
        (
            "Mozilla/5.0 (Windows NT 10.0) AppleWebKit Chrome/140.0 Safari/537.36",
            "Chrome on Windows",
        ),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) AppleWebKit Version/18.0 Safari/604.1",
            "Safari on iOS",
        ),
        (
            "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0",
            "Firefox on Linux",
        ),
        (
            "Mozilla/5.0 (Linux; Android 15) Chrome/140.0 Mobile Safari/537.36 Edg/140.0",
            "Edge on Android",
        ),
        ("", "Unknown browser on unknown OS"),
    ],
)
def test_user_agent_summary_is_family_only(ua, summary):
    assert user_agent_summary(ua) == summary


def test_sentry_scrubber_drops_bodies_cookies_and_secret_keys():
    event = {
        "request": {
            "url": "https://admin.example.com/api/v1/auth/login/",
            "data": {"password": "hunter2"},
            "cookies": {"sessionid": "abc"},
            "query_string": "token=raw",
            "headers": {"Cookie": "x", "X-CSRFToken": "y", "User-Agent": "ua"},
        },
        "extra": {"manual_key": "ABCD EFGH", "recovery_codes": ["X"], "safe": 1},
        "breadcrumbs": {"values": [{"data": {"otp": "123456", "ok": True}}]},
    }
    out = scrub_event(event)
    text = repr(out)
    for secret in ("hunter2", "abc", "token=raw", "ABCD EFGH", "123456", "'y'"):
        assert secret not in text
    assert out["request"]["headers"] == {"User-Agent": "ua"}
    assert out["extra"]["safe"] == 1


def test_api_responses_are_not_cacheable(client):
    response = client.get("/api/v1/system/health/")
    assert response["Cache-Control"] == "no-store"
    assert client.get("/healthz").get("Cache-Control") is None
