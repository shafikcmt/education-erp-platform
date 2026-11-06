"""Field-level encryption and keyed blind indexes (ADR-031, ADR-036).

* **Encryption:** AES-256-GCM through ``cryptography``. ``FIELD_ENCRYPTION_KEYS`` is a key ring
  of ``"<key_id>:<urlsafe-base64 32-byte key>"`` entries. The **first** key encrypts; every key
  decrypts, so keys can be rotated with ``rotate_field_encryption`` without downtime.
* **Ciphertext format (versioned):** ``0x01 | len(key_id) | key_id | nonce(12) | ciphertext+tag``.
* **Associated data (AAD):** every call names a ``purpose`` (e.g. ``"identity.mfadevice.secret"``),
  bound into the GCM tag. A ciphertext copied into another column fails to decrypt.
* **Blind index:** ``HMAC-SHA256(IP_INDEX_KEY, purpose || 0x00 || value)``. Exact-match search
  without decryption, and the keyed hash used for throttle keys and device fingerprints. A
  plain hash of an IPv4 address would be trivially brute-forced; the key prevents that.

Plaintext and keys are never logged. Production keys come from a secret manager (ADR-019);
``config.settings.prod`` refuses to start without real keys.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

_VERSION = 1
_NONCE_BYTES = 12
_KEY_BYTES = 32


class DecryptionError(Exception):
    """Ciphertext is malformed, was produced for another purpose, or its key is unknown."""


@dataclass(frozen=True)
class KeyRing:
    primary_id: str
    keys: dict[str, bytes]


def _decode_key(raw: str) -> bytes:
    padded = raw + "=" * (-len(raw) % 4)
    try:
        key = base64.urlsafe_b64decode(padded)
    except ValueError as exc:  # binascii.Error is a ValueError
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS contains an invalid key.") from exc
    if len(key) != _KEY_BYTES:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS entries must be 32-byte keys.")
    return key


def parse_key_ring(entries: list[str] | tuple[str, ...]) -> KeyRing:
    """Parse ``["kid:base64key", ...]``; the first entry is the encryption key."""
    if not entries:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS must contain at least one key.")
    keys: dict[str, bytes] = {}
    primary = ""
    for entry in entries:
        key_id, sep, encoded = entry.strip().partition(":")
        if not sep or not key_id or len(key_id) > 32 or not key_id.isascii():
            raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS entries must be 'key_id:key'.")
        if key_id in keys:
            raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS contains a duplicate key id.")
        keys[key_id] = _decode_key(encoded)
        primary = primary or key_id
    return KeyRing(primary_id=primary, keys=keys)


@lru_cache(maxsize=4)
def _ring_for(entries: tuple[str, ...]) -> KeyRing:
    return parse_key_ring(entries)


def key_ring() -> KeyRing:
    return _ring_for(tuple(settings.FIELD_ENCRYPTION_KEYS))


def _index_key() -> bytes:
    raw = settings.IP_INDEX_KEY
    if not raw:
        raise ImproperlyConfigured("IP_INDEX_KEY must be set.")
    return _decode_key(raw)


def generate_key() -> str:
    """Return a new random key in the ``FIELD_ENCRYPTION_KEYS`` / ``IP_INDEX_KEY`` encoding."""
    return base64.urlsafe_b64encode(os.urandom(_KEY_BYTES)).decode().rstrip("=")


def encrypt(plaintext: bytes, *, purpose: str) -> bytes:
    """Encrypt ``plaintext`` with the primary key, binding ``purpose`` as associated data."""
    ring = key_ring()
    key_id = ring.primary_id.encode()
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(ring.keys[ring.primary_id]).encrypt(nonce, plaintext, purpose.encode())
    return bytes([_VERSION, len(key_id)]) + key_id + nonce + ciphertext


def key_id_of(blob: bytes) -> str:
    """Return the id of the key that produced ``blob`` (used by key rotation)."""
    if len(blob) < 2 or blob[0] != _VERSION:
        raise DecryptionError("Unsupported ciphertext format.")
    return blob[2 : 2 + blob[1]].decode()


def decrypt(blob: bytes | memoryview, *, purpose: str) -> bytes:
    """Decrypt a value produced by :func:`encrypt` for the same ``purpose``."""
    data = bytes(blob)
    key_id = key_id_of(data)
    start = 2 + data[1]
    nonce, ciphertext = data[start : start + _NONCE_BYTES], data[start + _NONCE_BYTES :]
    key = key_ring().keys.get(key_id)
    if key is None:
        raise DecryptionError("Ciphertext was produced with an unknown key.")
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, purpose.encode())
    except InvalidTag as exc:
        raise DecryptionError("Ciphertext failed authentication.") from exc


def encrypt_str(value: str, *, purpose: str) -> bytes:
    return encrypt(value.encode(), purpose=purpose)


def decrypt_str(blob: bytes | memoryview, *, purpose: str) -> str:
    return decrypt(blob, purpose=purpose).decode()


def blind_index(value: str, *, purpose: str) -> str:
    """Keyed, deterministic hex digest of ``value`` for exact-match lookup (ADR-036)."""
    message = purpose.encode() + b"\x00" + value.encode()
    return hmac.new(_index_key(), message, hashlib.sha256).hexdigest()
