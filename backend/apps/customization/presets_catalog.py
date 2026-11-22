"""Institution-type presets (Phase 5 M2; ADR-058).

Presets are repo files (``presets/*.yaml``), loaded and validated here and synced into
``customization_preset`` by the owner-run bootstrap (``sync_presets``). A preset is immutable
once synced: changing it means a new version (``<type>.<variant>.v<N+1>``), which existing
institutions adopt only by opting in.

A preset's ``settings`` are values of declared keys (validated like an institution's
configuration); ``suggested_modules`` must be known, non-platform modules; exactly one preset
per institution type is ``default_for_type``.
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from apps.customization.registry import declared_settings

PRESET_DIR = Path(__file__).resolve().parent / "presets"
CODE_PATTERN = re.compile(r"^[a-z][a-z_]*\.[a-z][a-z0-9_]*\.v([1-9][0-9]*)$")
TYPE_PREFIX = {
    "school": "school",
    "college": "college",
    "university": "university",
    "madrasa": "madrasa",
    "coaching_center": "coaching",
    "training_institute": "training",
}
_TOP_KEYS = {
    "code",
    "institution_type",
    "version",
    "default_for_type",
    "name",
    "suggested_modules",
    "settings",
}


class InvalidPresetError(ValueError):
    pass


def checksum(content: dict[str, Any]) -> str:
    canonical = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def validate_preset(raw: Any, *, source: str = "preset") -> dict[str, Any]:
    from apps.module_registry.registry import declared_modules

    if not isinstance(raw, dict) or set(raw) - _TOP_KEYS:
        raise InvalidPresetError(f"{source}: unknown or missing top-level keys.")
    code = raw.get("code", "")
    match = CODE_PATTERN.match(code) if isinstance(code, str) else None
    itype = raw.get("institution_type")
    if match is None or itype not in TYPE_PREFIX or not code.startswith(f"{TYPE_PREFIX[itype]}."):
        raise InvalidPresetError(f"{source}: code must be '<type>.<variant>.v<N>' of its type.")
    if raw.get("version") != int(match.group(1)):
        raise InvalidPresetError(f"{source}: version must match the code.")
    name = raw.get("name")
    if not isinstance(name, dict) or not all(isinstance(v, str) and v for v in name.values()):
        raise InvalidPresetError(f"{source}: name is a map of locale to text.")
    modules = declared_modules()
    suggested = raw.get("suggested_modules", [])
    bad = [m for m in suggested if m not in modules or modules[m].category == "platform"]
    if bad:
        raise InvalidPresetError(f"{source}: unknown or platform modules suggested: {bad}.")
    specs = declared_settings()
    settings = raw.get("settings", {})
    if not isinstance(settings, dict):
        raise InvalidPresetError(f"{source}: settings is a map of declared keys.")
    for key, value in settings.items():
        spec = specs.get(key)
        if spec is None or "institution" not in spec.scopes:
            raise InvalidPresetError(f"{source}: {key!r} is not an institution setting.")
        if next(iter(spec.validator().iter_errors(value)), None) is not None:
            raise InvalidPresetError(f"{source}: invalid value for {key!r}.")
    return {
        "code": code,
        "institution_type": itype,
        "version": raw["version"],
        "default_for_type": bool(raw.get("default_for_type", False)),
        "name": name,
        "suggested_modules": list(suggested),
        "settings": settings,
    }


@cache
def file_presets() -> dict[str, dict[str, Any]]:
    """Every preset file, validated; exactly one default per institution type."""
    presets: dict[str, dict[str, Any]] = {}
    for path in sorted(PRESET_DIR.glob("*.yaml")):
        with path.open(encoding="utf-8") as handle:
            preset = validate_preset(yaml.safe_load(handle), source=path.name)
        if path.name != f"{preset['code']}.yaml":
            raise InvalidPresetError(f"{path.name}: the file is named after its code.")
        presets[preset["code"]] = preset
    for itype in TYPE_PREFIX:
        defaults = [
            p for p in presets.values() if p["institution_type"] == itype and p["default_for_type"]
        ]
        if len(defaults) != 1:
            raise InvalidPresetError(f"{itype}: exactly one default preset is required.")
    return presets
