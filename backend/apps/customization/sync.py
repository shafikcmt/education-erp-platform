"""Owner-only, idempotent sync of the preset catalogue (Phase 5 M2; ADR-058; P21).

Runs in the one-shot ``migrate`` bootstrap step as the database owner, like ``sync_modules``.
A synced preset is immutable: a file whose content changed for an existing code is refused
(publish a new version instead). Presets removed from the repo are deprecated, never deleted
(institutions stay pinned to them). Every run is audited.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.audit.models import ActorType
from apps.audit.services import record
from apps.core.db_operations import require_owner_role
from apps.customization.models import Preset
from apps.customization.presets_catalog import InvalidPresetError, checksum, file_presets


@dataclass
class PresetSyncResult:
    declared: int = 0
    created: int = 0
    deprecated: int = 0


@transaction.atomic
def sync_presets() -> PresetSyncResult:
    require_owner_role("sync_presets")
    presets = file_presets()
    result = PresetSyncResult(declared=len(presets))
    existing = {p.code: p for p in Preset.objects.select_for_update()}
    # Defaults move only between active presets: clear first, then set (one-default rule).
    Preset.objects.filter(is_default=True).exclude(
        code__in=[c for c, p in presets.items() if p["default_for_type"]]
    ).update(is_default=False)
    for code, preset in presets.items():
        content = {"suggested_modules": preset["suggested_modules"], "settings": preset["settings"]}
        digest = checksum(content)
        row = existing.get(code)
        if row is None:
            Preset.objects.create(
                code=code,
                institution_type=preset["institution_type"],
                version=preset["version"],
                is_default=preset["default_for_type"],
                name=preset["name"],
                content=content,
                checksum=digest,
            )
            result.created += 1
        elif row.checksum != digest:
            raise InvalidPresetError(f"{code}: synced presets are immutable; add a new version.")
        elif row.is_default != preset["default_for_type"] or row.deprecated_at is not None:
            row.is_default, row.deprecated_at = preset["default_for_type"], None
            row.save(update_fields=["is_default", "deprecated_at", "updated_at"])
    for code, row in existing.items():
        if code not in presets and row.deprecated_at is None:
            row.deprecated_at, row.is_default = timezone.now(), False
            row.save(update_fields=["deprecated_at", "is_default", "updated_at"])
            result.deprecated += 1
    record(
        "customization.presets.synced",
        actor_type=ActorType.SYSTEM,
        metadata={
            "declared": result.declared,
            "created": result.created,
            "deprecated": result.deprecated,
        },
    )
    return result
