"""Malware scanning hook (Phase 6 M3; ADR-064, ADR-066 Q8).

``FILES_SCANNER`` names a callable ``(key) -> "clean" | "infected" | "unscanned"``. The default
does not scan: files stay ``unscanned``, are downloadable by staff only (with a warning) and
never by applicants. A real scanner is an infrastructure decision for Phase 18.
"""

from __future__ import annotations

from django.conf import settings
from django.utils.module_loading import import_string


def no_scanner(key: str) -> str:
    return "unscanned"


def scan(key: str) -> str:
    result = str(
        import_string(getattr(settings, "FILES_SCANNER", "apps.files.scanning.no_scanner"))(key)
    )
    return result if result in {"clean", "infected", "unscanned"} else "unscanned"
