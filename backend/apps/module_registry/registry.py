"""Module manifests (Phase 4 M1; ADR-050).

Each project app may declare ``MODULE = {...}`` in its ``manifest.py`` (next to
``PERMISSIONS``)::

    MODULE = {"code": "tenancy", "name": "Tenancy", "category": "platform",
              "version": "1.0.0", "dependencies": ["identity", "rbac"], "sellable": False}

:func:`declared_modules` merges the installed manifests with the planned catalogue
(:mod:`apps.module_registry.catalog`) and validates the whole set: canonical codes, known
categories, known dependencies, no cycles, platform modules never sellable and never
depending on sellable ones. An invalid catalogue raises at sync time and fails CI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import import_module
from typing import Any

from django.apps import apps

from apps.module_registry.catalog import EXTENSION, PLANNED_MODULES, PLATFORM, STANDARD

CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
CATEGORIES = (PLATFORM, STANDARD, EXTENSION)
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


class InvalidModuleCatalog(ValueError):  # noqa: N818 - a ValueError family member
    pass


@dataclass(frozen=True)
class ModuleSpec:
    code: str
    name: str
    category: str
    version: str
    dependencies: tuple[str, ...]
    sellable: bool
    available: bool  # True: the module's code is installed


def _spec(raw: dict[str, Any], *, available: bool) -> ModuleSpec:
    code = raw.get("code", "")
    if not isinstance(code, str) or not CODE_PATTERN.match(code):
        raise InvalidModuleCatalog(f"Invalid module code {code!r}.")
    category = raw.get("category")
    if category not in CATEGORIES:
        raise InvalidModuleCatalog(f"{code}: unknown category {category!r}.")
    version = str(raw.get("version", ""))
    if not VERSION_PATTERN.match(version):
        raise InvalidModuleCatalog(f"{code}: version must be MAJOR.MINOR.PATCH.")
    deps = tuple(raw.get("dependencies", ()))
    if code in deps:
        raise InvalidModuleCatalog(f"{code}: depends on itself.")
    sellable = bool(raw.get("sellable", False))
    if category == PLATFORM and sellable:
        raise InvalidModuleCatalog(f"{code}: platform modules are never sold separately.")
    return ModuleSpec(
        code=code,
        name=str(raw.get("name") or code),
        category=category,
        version=version,
        dependencies=deps,
        sellable=sellable,
        available=available,
    )


def installed_manifests() -> dict[str, ModuleSpec]:
    specs: dict[str, ModuleSpec] = {}
    for config in apps.get_app_configs():
        if not config.name.startswith("apps."):
            continue
        try:
            manifest = import_module(f"{config.name}.manifest")
        except ModuleNotFoundError as exc:
            if exc.name == f"{config.name}.manifest":
                continue
            raise
        raw = getattr(manifest, "MODULE", None)
        if raw is None:
            continue
        spec = _spec(raw, available=True)
        if spec.code != config.label:
            raise InvalidModuleCatalog(
                f"{config.name}: MODULE code {spec.code!r} must equal the app label."
            )
        specs[spec.code] = spec
    return specs


def declared_modules() -> dict[str, ModuleSpec]:
    """Installed manifests plus the planned catalogue, validated as one graph."""
    specs = installed_manifests()
    for raw in PLANNED_MODULES:
        spec = _spec(raw, available=False)
        specs.setdefault(spec.code, spec)
    for spec in specs.values():
        missing = [d for d in spec.dependencies if d not in specs]
        if missing:
            raise InvalidModuleCatalog(f"{spec.code}: unknown dependencies {missing}.")
        if spec.category == PLATFORM:
            sold = [d for d in spec.dependencies if specs[d].sellable]
            if sold:
                raise InvalidModuleCatalog(f"{spec.code}: platform module depends on {sold}.")
    _assert_acyclic(specs)
    return dict(sorted(specs.items()))


def _assert_acyclic(specs: dict[str, ModuleSpec]) -> None:
    state: dict[str, int] = {}  # 1 = visiting, 2 = done

    def visit(code: str, path: tuple[str, ...]) -> None:
        if state.get(code) == 2:
            return
        if state.get(code) == 1:
            raise InvalidModuleCatalog(f"Dependency cycle: {' -> '.join((*path, code))}.")
        state[code] = 1
        for dep in specs[code].dependencies:
            visit(dep, (*path, code))
        state[code] = 2

    for code in specs:
        visit(code, ())


def dependency_closure(codes: set[str], specs: dict[str, ModuleSpec]) -> set[str]:
    """``codes`` plus everything they depend on, transitively (unknown codes are dropped)."""
    result: set[str] = set()
    stack = [c for c in codes if c in specs]
    while stack:
        code = stack.pop()
        if code in result:
            continue
        result.add(code)
        stack.extend(specs[code].dependencies)
    return result
