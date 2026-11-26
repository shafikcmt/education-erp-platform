"""File purposes declared by modules (``FILE_PURPOSES`` in a manifest; ADR-064).

``{code: {"types": [...], "max_bytes": int, "max_per_owner": int, "applicant_visible": bool}}``.
A file can only be stored for a declared purpose, within its limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from importlib import import_module
from typing import Any

from django.apps import apps

# Content types a purpose may allow. Anything that a browser could render as active content
# (HTML, SVG, scripts) is never storable.
SAFE_TYPES = frozenset(
    {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/webp",
        "text/csv",
        "text/plain",
        # Phase 7 M6 (ADR-072): spreadsheets for bulk import. Never rendered by browsers (always
        # served as attachments); parsed server-side read-only with size limits.
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
)
MAX_BYTES = 50 * 1024 * 1024


class InvalidPurposeError(Exception):
    """A manifest declares an invalid file purpose."""


@dataclass(frozen=True)
class Purpose:
    code: str
    types: frozenset[str]
    max_bytes: int
    max_per_owner: int
    applicant_visible: bool = False


def _purpose(code: str, raw: dict[str, Any]) -> Purpose:
    types = frozenset(raw.get("types", ()))
    if not types or not types <= SAFE_TYPES:
        raise InvalidPurposeError(
            f"{code}: types must be a non-empty subset of {sorted(SAFE_TYPES)}."
        )
    max_bytes, per_owner = int(raw.get("max_bytes", 0)), int(raw.get("max_per_owner", 0))
    if not 0 < max_bytes <= MAX_BYTES or not 0 < per_owner <= 100:
        raise InvalidPurposeError(f"{code}: max_bytes (≤ 50 MB) and max_per_owner (≤ 100) needed.")
    return Purpose(code, types, max_bytes, per_owner, bool(raw.get("applicant_visible", False)))


@cache
def declared_purposes() -> dict[str, Purpose]:
    out: dict[str, Purpose] = {}
    for config in apps.get_app_configs():
        if not config.name.startswith("apps."):
            continue
        try:
            manifest = import_module(f"{config.name}.manifest")
        except ModuleNotFoundError as exc:
            if exc.name == f"{config.name}.manifest":
                continue
            raise
        for code, raw in getattr(manifest, "FILE_PURPOSES", {}).items():
            if code in out:
                raise InvalidPurposeError(f"Duplicate file purpose {code!r}.")
            out[code] = _purpose(code, raw)
    return out
