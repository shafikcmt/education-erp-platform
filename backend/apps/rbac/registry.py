"""Permission registry built from module manifests (Phase 2 plan §5.1).

Each module app may define ``<app>/manifest.py`` with a ``PERMISSIONS`` list of plain dicts::

    PERMISSIONS = [
        {"code": "identity.user.view", "description": "...", "requires_mfa": True},
    ]

Codes follow ``<module>.<resource>.<action>`` and must start with the app label.
``manage.py sync_permissions`` writes the registry into ``rbac_permission``.
"""

import re
from dataclasses import dataclass
from importlib import import_module
from typing import Any

from django.apps import apps

CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class PermissionSpec:
    code: str
    module_code: str
    description: str
    is_sensitive: bool = False
    requires_mfa: bool = False
    requires_step_up: bool = False


def _spec(module_code: str, raw: dict[str, Any]) -> PermissionSpec:
    code = raw["code"]
    if not CODE_PATTERN.match(code) or not code.startswith(f"{module_code}."):
        raise ValueError(f"Invalid permission code {code!r} in module {module_code!r}")
    return PermissionSpec(
        code=code,
        module_code=module_code,
        description=raw["description"],
        is_sensitive=bool(raw.get("is_sensitive", False)),
        requires_mfa=bool(raw.get("requires_mfa", False)),
        requires_step_up=bool(raw.get("requires_step_up", False)),
    )


def declared_permissions() -> dict[str, PermissionSpec]:
    """Collect every manifest permission of the installed project apps."""
    specs: dict[str, PermissionSpec] = {}
    for config in apps.get_app_configs():
        if not config.name.startswith("apps."):
            continue
        try:
            manifest = import_module(f"{config.name}.manifest")
        except ModuleNotFoundError as exc:
            if exc.name == f"{config.name}.manifest":
                continue
            raise
        for raw in getattr(manifest, "PERMISSIONS", []):
            spec = _spec(config.label, raw)
            if spec.code in specs:
                raise ValueError(f"Duplicate permission code {spec.code!r}")
            specs[spec.code] = spec
    return specs
