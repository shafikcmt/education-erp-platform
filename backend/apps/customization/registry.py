"""Declared configuration keys (Phase 5 M1; ADR-057).

Each installed module may declare ``SETTINGS`` in its manifest: ``{key: spec}`` where ``key``
starts with the module code, and ``spec`` holds a JSON Schema (``schema``), a ``default`` that
validates, the ``scopes`` where a value may be set (tenant / institution / campus) and a
``merge`` strategy (``replace`` or ``deep`` for objects). Undeclared keys are rejected
everywhere; the catalogue is validated in CI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from importlib import import_module
from typing import Any

from django.apps import apps

# jsonschema ships no type information (no stub package added: ADR-057 keeps dependencies lean).
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import SchemaError  # type: ignore[import-untyped]

SCOPES = ("tenant", "institution", "campus")
MERGES = ("replace", "deep")
KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_.]{1,79}$")


class InvalidSettingsCatalogError(ValueError):
    pass


@dataclass(frozen=True)
class SettingSpec:
    key: str
    schema: dict[str, Any]
    default: Any
    scopes: tuple[str, ...]
    merge: str
    description: str

    def validator(self) -> Draft202012Validator:
        return _validator(self.key)


def _spec(module: str, key: str, raw: dict[str, Any]) -> SettingSpec:
    if not KEY_PATTERN.match(key) or not key.startswith(f"{module}."):
        raise InvalidSettingsCatalogError(f"{key!r}: keys are '<module>.<name>' of their module.")
    schema = raw.get("schema")
    if not isinstance(schema, dict):
        raise InvalidSettingsCatalogError(f"{key}: a JSON Schema is required.")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise InvalidSettingsCatalogError(f"{key}: invalid schema ({exc.message}).") from None
    scopes = tuple(raw.get("scopes", ()))
    if not scopes or any(s not in SCOPES for s in scopes):
        raise InvalidSettingsCatalogError(f"{key}: scopes must be a non-empty subset of {SCOPES}.")
    merge = raw.get("merge", "replace")
    if merge not in MERGES or (merge == "deep" and schema.get("type") != "object"):
        raise InvalidSettingsCatalogError(f"{key}: merge is 'replace', or 'deep' for objects.")
    if "default" not in raw:
        raise InvalidSettingsCatalogError(f"{key}: a default is required.")
    errors = list(Draft202012Validator(schema).iter_errors(raw["default"]))
    if errors:
        raise InvalidSettingsCatalogError(f"{key}: the default does not validate.")
    return SettingSpec(
        key=key,
        schema=schema,
        default=raw["default"],
        scopes=scopes,
        merge=merge,
        description=str(raw.get("description", "")),
    )


@cache
def declared_settings() -> dict[str, SettingSpec]:
    specs: dict[str, SettingSpec] = {}
    for config in apps.get_app_configs():
        if not config.name.startswith("apps."):
            continue
        try:
            manifest = import_module(f"{config.name}.manifest")
        except ModuleNotFoundError as exc:
            if exc.name == f"{config.name}.manifest":
                continue
            raise
        for key, raw in getattr(manifest, "SETTINGS", {}).items():
            if key in specs:
                raise InvalidSettingsCatalogError(f"Duplicate setting {key!r}.")
            specs[key] = _spec(config.label, key, raw)
    return specs


@cache
def _validator(key: str) -> Draft202012Validator:
    return Draft202012Validator(declared_settings()[key].schema)
