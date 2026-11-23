"""Configuration publish check (Phase 6 M1; ADR-063).

Registered in ``CUSTOMIZATION_PUBLISH_CHECKS``: ``customization`` calls it after a new
configuration version becomes active, inside the same transaction, so a failure undoes the
publish. ``customization`` never imports ``academics``.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError

from apps.academics.capabilities import unit_levels
from apps.academics.models import Unit


def check_structure_levels(scope: Any) -> None:
    """Units in use must keep their level, and each child stays one level below its parent."""
    rows = Unit.objects.filter(archived_at__isnull=True)
    if scope.institution_id is not None:
        rows = rows.filter(institution_id=scope.institution_id)
    used: dict[Any, set[tuple[str, str | None]]] = {}
    for inst, key, parent_key in rows.values_list(
        "institution_id", "level_key", "parent__level_key"
    ).distinct():
        used.setdefault(inst, set()).add((key, parent_key))
    for inst, pairs in used.items():
        levels = unit_levels(inst)
        for level, parent_level in pairs:
            if level not in levels:
                raise ValidationError(
                    {"customization.structure_levels": f"Level {level!r} is used by units."}
                )
            index = levels.index(level)
            expected = levels[index - 1] if index else None
            if parent_level != expected:
                raise ValidationError(
                    {
                        "customization.structure_levels": (
                            f"Units at level {level!r} would no longer sit one level below "
                            "their parents."
                        )
                    }
                )
