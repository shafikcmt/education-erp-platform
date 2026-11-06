"""Encrypted storage of client IP addresses (ADR-036; Phase 2 plan §6.9).

Every table that keeps an IP stores the same triple:

* ``ip_encrypted`` — AES-GCM ciphertext (ADR-031 key ring), decrypted only for an audited reveal;
* ``ip_index`` — keyed HMAC blind index for exact-match forensic search without decryption;
* ``ip_prefix`` — coarse network (IPv4 /24, IPv6 /48), the only part kept after anonymisation.
"""

from dataclasses import dataclass

from apps.core import crypto
from apps.core.net import ip_prefix, normalize_ip

IP_PURPOSE = "security.ip"
IP_INDEX_PURPOSE = "security.ip.index"


@dataclass(frozen=True)
class SealedIP:
    ip_encrypted: bytes | None
    ip_index: str | None
    ip_prefix: str


EMPTY = SealedIP(ip_encrypted=None, ip_index=None, ip_prefix="")


def seal_ip(value: str) -> SealedIP:
    normalised = normalize_ip(value)
    if not normalised:
        return EMPTY
    return SealedIP(
        ip_encrypted=crypto.encrypt_str(normalised, purpose=IP_PURPOSE),
        ip_index=ip_search_index(normalised),
        ip_prefix=ip_prefix(normalised),
    )


def ip_search_index(value: str) -> str:
    """Blind index of an IP, for "find every event from this address" searches."""
    return crypto.blind_index(normalize_ip(value), purpose=IP_INDEX_PURPOSE)


def open_ip(ciphertext: bytes | memoryview | None) -> str:
    """Decrypt a sealed IP. Callers must have checked ``audit.event.view_ip`` + step-up."""
    if not ciphertext:
        return ""
    return crypto.decrypt_str(ciphertext, purpose=IP_PURPOSE)
