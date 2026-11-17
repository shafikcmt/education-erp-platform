"""Request network helpers: client IP, IP normalisation/masking, user-agent summary.

IP addresses are personal data (ADR-036): callers store them only through the encrypted
fields, and API responses show :func:`mask_ip` output unless a reveal is authorised.
"""

import ipaddress
import re

from django.conf import settings
from django.http import HttpRequest


def client_ip(request: HttpRequest) -> str:
    """Return the client IP as seen by the trusted reverse proxy, else ``REMOTE_ADDR``.

    ``CLIENT_IP_HEADER`` names a header the proxy **overwrites** (Nginx sets
    ``X-Real-IP $remote_addr``), so clients cannot spoof it. Invalid values are ignored.
    """
    header = getattr(settings, "CLIENT_IP_HEADER", "")
    candidates = [request.META.get(header, "")] if header else []
    candidates.append(request.META.get("REMOTE_ADDR", ""))
    for candidate in candidates:
        normalised = normalize_ip(candidate)
        if normalised:
            return normalised
    return ""


def normalize_ip(value: str) -> str:
    """Canonical text form (IPv4-mapped IPv6 → IPv4), or ``""`` when invalid."""
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return ""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return str(address)


def ip_prefix(value: str) -> str:
    """Coarse network kept after anonymisation: IPv4 /24, IPv6 /48 (ADR-036)."""
    normalised = normalize_ip(value)
    if not normalised:
        return ""
    address = ipaddress.ip_address(normalised)
    bits = 24 if address.version == 4 else 48
    return str(ipaddress.ip_network(f"{normalised}/{bits}", strict=False))


def mask_ip(value: str) -> str:
    """Display form that hides the host part: ``203.0.113.•`` / ``2001:db8:85a3::•``."""
    normalised = normalize_ip(value)
    if not normalised:
        return ""
    address = ipaddress.ip_address(normalised)
    if address.version == 4:
        return ".".join(normalised.split(".")[:3]) + ".•"
    network = ipaddress.ip_network(f"{normalised}/48", strict=False)
    return str(network.network_address).rstrip(":") + "::•"


def mask_prefix(prefix: str) -> str:
    """Display form of a stored prefix (after anonymisation the prefix is all that remains)."""
    return mask_ip(prefix.split("/", 1)[0]) if prefix else ""


_BROWSERS = (
    ("Edge", re.compile(r"Edg(?:e|A|iOS)?/")),
    ("Opera", re.compile(r"OPR/|Opera")),
    ("Samsung Internet", re.compile(r"SamsungBrowser/")),
    ("Firefox", re.compile(r"Firefox/|FxiOS/")),
    ("Chrome", re.compile(r"Chrome/|CriOS/")),
    ("Safari", re.compile(r"Safari/")),
)
_SYSTEMS = (
    ("iOS", re.compile(r"iPhone|iPad|iPod")),
    ("Android", re.compile(r"Android")),
    ("Windows", re.compile(r"Windows")),
    ("macOS", re.compile(r"Mac OS X|Macintosh")),
    ("ChromeOS", re.compile(r"CrOS")),
    ("Linux", re.compile(r"Linux")),
)


def user_agent_summary(user_agent: str) -> str:
    """Browser and OS **family** only (e.g. ``"Firefox on Linux"``), never the raw string."""
    ua = user_agent[:512]
    browser = next((name for name, pattern in _BROWSERS if pattern.search(ua)), "Unknown browser")
    system = next((name for name, pattern in _SYSTEMS if pattern.search(ua)), "unknown OS")
    return f"{browser} on {system}"


def normalize_host(raw: str) -> str:
    """Lower-case host name without its port (``""`` when it can't be parsed).

    Used wherever hosts are compared (host policy, session-host binding), so ``Acme.Test:8443``
    and ``acme.test`` are the same host. A trailing dot is kept: it is a different cookie host.
    """
    host = (raw or "").strip().lower()
    if host.startswith("["):  # bracketed IPv6 literal, optionally with a port
        end = host.find("]")
        return host[: end + 1] if end > 0 else ""
    if host.count(":") == 1:
        host = host.split(":", 1)[0]
    elif ":" in host:
        return ""
    return host
