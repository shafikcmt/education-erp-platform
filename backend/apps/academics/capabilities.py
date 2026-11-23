"""The one place where academics reads institution configuration (CLAUDE.md §4; ADR-063).

Code branches on capability flags read here, never on the institution type. The unit levels
are the institution's effective ``customization.structure_levels``; keys that name a time or
subject dimension (listed v1 presets mixed them in) are not unit levels: those dimensions have
their own models.
"""

from __future__ import annotations

import uuid

from apps.customization.resolver import get_effective_config
from apps.customization.scopes import ConfigScope

CREDIT_BASED = "academics.credit_based"
SEMESTER_BASED = "academics.semester_based"
SECTION_ENABLED = "academics.section_enabled"

# Time and subject dimensions with their own models (v1 presets listed them as levels).
NON_UNIT_LEVELS = frozenset(
    {"academic_year", "session", "semester", "term", "subject", "course", "kitab", "module"}
)


def capability(institution_id: uuid.UUID, flag: str) -> bool:
    flags = get_effective_config(ConfigScope(institution_id), "customization.capabilities")
    return bool((flags or {}).get(flag, False))


def unit_levels(institution_id: uuid.UUID) -> list[str]:
    """Organisational levels of the institution, broadest first."""
    levels = get_effective_config(ConfigScope(institution_id), "customization.structure_levels")
    return [lv["key"] for lv in levels or [] if lv["key"] not in NON_UNIT_LEVELS]
