"""Per-plan Studio quotas (Phase 5 M6; ADR-060 Q5: soft limits).

The limit of each artefact comes from the tenant's plan (``limits`` keys below) or the platform
default in ``STUDIO_QUOTA_DEFAULTS``. Lists report ``{used, limit}`` so the Studio can warn
early; creating a new artefact at the limit is refused (``quota_exceeded``). Existing artefacts
are never removed or disabled when a plan shrinks.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.module_loading import import_string

from apps.core.tenancy import require_tenant


def limit(key: str) -> int:
    defaults = dict(getattr(settings, "STUDIO_QUOTA_DEFAULTS", {}))
    hook = getattr(settings, "TENANCY_PLAN_LIMITS", "")
    plan = import_string(hook)(require_tenant().id) if hook else {}
    value = plan.get(key, defaults.get(key))
    return int(value) if value is not None else 0


def status(key: str, used: int) -> dict[str, int]:
    return {"used": used, "limit": limit(key)}


def check(key: str, used: int) -> None:
    """Refuse a new artefact when ``used`` has reached the limit."""
    cap = limit(key)
    if cap and used >= cap:
        raise ValidationError(
            {"quota": f"Your plan allows {cap} of these ({key}). Archive one or upgrade."}
        )
