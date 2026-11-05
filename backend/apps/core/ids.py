"""Identifier generation — the ONLY place that may import the UUIDv7 library (ADR-012).

All primary keys and request IDs are created through :func:`new_id`. The import-linter
contract in ``pyproject.toml`` forbids importing ``uuid_utils`` anywhere else, so swapping
the implementation (e.g. to the stdlib ``uuid.uuid7`` after a Python upgrade) is a one-file
change.
"""

import uuid

from uuid_utils import compat as _uuid_compat


def new_id() -> uuid.UUID:
    """Return a new RFC 9562 UUIDv7 as a standard-library :class:`uuid.UUID`.

    UUIDv7 values are time-ordered (good B-tree locality) and not enumerable. They embed the
    creation timestamp, so they are identifiers, never secrets or authorization tokens.
    """
    value = _uuid_compat.uuid7()
    # Normalise to a plain stdlib UUID instance regardless of library internals.
    return uuid.UUID(bytes=value.bytes)
