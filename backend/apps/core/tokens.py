"""Single-use secret tokens for email links and invitations (ADR-034).

Only the SHA-256 hash of a token is stored; lookups are by hash. The raw token exists only
in the email link (URL fragment) and in the request that redeems it, and is never logged.
Reused by Phase 3 tenant invitations, which keep their own (RLS-protected) table.
"""

import hashlib
import secrets

TOKEN_BYTES = 32  # 256 bits of randomness


def hash_token(raw: str) -> str:
    """Return the hex SHA-256 of a raw token (64 characters)."""
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_token() -> tuple[str, str]:
    """Return ``(raw_token, token_hash)``. Store only the hash."""
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    return raw, hash_token(raw)
