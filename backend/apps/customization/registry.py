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

# jsonschema ships no type information (no stub package added: ADR-057 keeps dependencies lean).
from typing import TYPE_CHECKING, Any

from django.apps import apps
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import SchemaError  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from apps.customization.rules import Namespace

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


def _manifest_items(attribute: str) -> list[tuple[str, str, Any]]:
    out: list[tuple[str, str, Any]] = []
    for config in apps.get_app_configs():
        if not config.name.startswith("apps."):
            continue
        try:
            manifest = import_module(f"{config.name}.manifest")
        except ModuleNotFoundError as exc:
            if exc.name == f"{config.name}.manifest":
                continue
            raise
        out.extend(
            (config.label, key, raw) for key, raw in getattr(manifest, attribute, {}).items()
        )
    return out


@cache
def declared_namespaces() -> dict[str, Namespace]:
    """Rule namespaces of the installed modules (ADR-055)."""
    from apps.customization.rules import Namespace

    out: dict[str, Namespace] = {}
    for module, code, raw in _manifest_items("RULE_NAMESPACES"):
        if not KEY_PATTERN.match(code) or not code.startswith(f"{module}."):
            raise InvalidSettingsCatalogError(f"{code!r}: namespaces are '<module>.<name>'.")
        if raw.get("result") not in ("boolean", "number", "any") or not raw.get("variables"):
            raise InvalidSettingsCatalogError(f"{code}: result type and variables are required.")
        out[code] = Namespace(
            code=code,
            variables=tuple(raw["variables"]),
            result=raw["result"],
            description=str(raw.get("description", "")),
        )
    return out


@cache
def declared_entities() -> dict[str, str]:
    """Entities that accept custom fields: code -> label (owned by the declaring module)."""
    out: dict[str, str] = {}
    for module, code, raw in _manifest_items("CUSTOM_FIELD_ENTITIES"):
        if not KEY_PATTERN.match(code) or not code.startswith(f"{module}."):
            raise InvalidSettingsCatalogError(f"{code!r}: entities are '<module>.<name>'.")
        out[code] = str(raw.get("label", code))
    return out


@cache
def entity_core_fields() -> dict[str, frozenset[str]]:
    """Core (non-custom) fields a form may place, per declared entity."""
    return {
        code: frozenset(raw.get("core_fields", []))
        for _, code, raw in _manifest_items("CUSTOM_FIELD_ENTITIES")
    }


@cache
def declared_subjects() -> dict[str, str]:
    """Subjects that approval workflows may run on (``WORKFLOW_SUBJECTS``)."""
    out: dict[str, str] = {}
    for module, code, raw in _manifest_items("WORKFLOW_SUBJECTS"):
        if not KEY_PATTERN.match(code) or not code.startswith(f"{module}."):
            raise InvalidSettingsCatalogError(f"{code!r}: subjects are '<module>.<name>'.")
        out[code] = str(raw.get("label", code))
    return out
