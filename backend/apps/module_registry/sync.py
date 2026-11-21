"""Owner-only, idempotent sync of the module catalogue (Phase 4 M1; ADR-050).

Runs in the one-shot ``migrate`` bootstrap step as the database owner role, like
``sync_permissions`` (O1). Every run is audited (``module_registry.catalog.synced``).
:func:`catalog_drift` is the read-only check used by tests and runtime guards.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.audit.models import ActorType
from apps.audit.services import record
from apps.core.db_operations import require_owner_role
from apps.module_registry.models import Module
from apps.module_registry.registry import ModuleSpec, declared_modules

_FIELDS = ("name", "category", "version", "sellable", "available")


@dataclass
class ModuleSyncResult:
    created: int = 0
    updated: int = 0
    deprecated: int = 0
    declared: int = 0


def _values(spec: ModuleSpec) -> dict[str, object]:
    values: dict[str, object] = {f: getattr(spec, f) for f in _FIELDS}
    values["dependencies"] = list(spec.dependencies)
    values["deprecated_at"] = None
    return values


@transaction.atomic
def sync_modules() -> ModuleSyncResult:
    require_owner_role("sync_modules")
    specs = declared_modules()
    result = ModuleSyncResult(declared=len(specs))
    existing = {m.code: m for m in Module.objects.select_for_update()}
    for code, spec in specs.items():
        values = _values(spec)
        row = existing.get(code)
        if row is None:
            Module.objects.create(code=code, **values)
            result.created += 1
        elif any(getattr(row, k) != v for k, v in values.items()):
            for key, value in values.items():
                setattr(row, key, value)
            row.save()
            result.updated += 1
    for code, row in existing.items():
        if code not in specs and row.deprecated_at is None:
            row.deprecated_at = timezone.now()
            row.save(update_fields=["deprecated_at", "updated_at"])
            result.deprecated += 1
    record(
        "module_registry.catalog.synced",
        actor_type=ActorType.SYSTEM,
        metadata={
            "created": result.created,
            "updated": result.updated,
            "deprecated": result.deprecated,
            "declared": result.declared,
        },
    )
    return result


def catalog_drift() -> list[str]:
    """Read-only: differences between the database and the declared module catalogue."""
    problems: list[str] = []
    rows = {m.code: m for m in Module.objects.all()}
    for code, spec in declared_modules().items():
        row = rows.get(code)
        if row is None:
            problems.append(f"module {code} missing")
        elif any(getattr(row, k) != v for k, v in _values(spec).items()):
            problems.append(f"module {code} out of date")
    return problems
