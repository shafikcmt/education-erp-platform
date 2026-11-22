"""Preset hooks used by other modules through settings (Phase 5 M2; ADR-058)."""

from __future__ import annotations

from typing import Any

from apps.customization.models import Preset
from apps.customization.scopes import ConfigScope


def default_preset_for(institution_type: str) -> tuple[str, str]:
    """``TENANCY_INSTITUTION_PRESET`` hook: the pinned (code, version) for a new institution."""
    row = (
        Preset.objects.filter(
            institution_type=institution_type, is_default=True, deprecated_at__isnull=True
        )
        .values_list("code", "version")
        .first()
    )
    return (row[0], str(row[1])) if row else ("", "")


def layer(scope: ConfigScope) -> dict[str, Any]:
    """``CUSTOMIZATION_PRESET_LAYER`` hook: the settings of the institution's pinned preset
    (below the tenant's own values, ADR-057). The tenant scope has no preset."""
    from apps.tenancy.models import Institution

    if scope.institution_id is None:
        return {}
    code = (
        Institution.objects.filter(pk=scope.institution_id)
        .values_list("preset_code", flat=True)
        .first()
    )
    if not code:
        return {}
    content = Preset.objects.filter(code=code).values_list("content", flat=True).first()
    settings = (content or {}).get("settings", {})
    return dict(settings) if isinstance(settings, dict) else {}
