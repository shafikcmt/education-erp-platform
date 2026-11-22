"""Configuration scopes of the current tenant (Phase 5 M1)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from apps.core.tenancy import require_tenant
from apps.rbac.engine import ScopeTarget


@dataclass(frozen=True)
class ConfigScope:
    """The whole tenant, one institution, or one campus of an institution."""

    institution_id: uuid.UUID | None = None
    campus_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if self.campus_id is not None and self.institution_id is None:
            raise ValueError("A campus scope needs its institution.")

    @property
    def kind(self) -> str:
        if self.campus_id is not None:
            return "campus"
        return "institution" if self.institution_id is not None else "tenant"

    def chain(self) -> list[ConfigScope]:
        """This scope and its parents, broadest first (resolution order, ADR-057)."""
        out = [ConfigScope()]
        if self.institution_id is not None:
            out.append(ConfigScope(self.institution_id))
        if self.campus_id is not None:
            out.append(self)
        return out

    def target(self) -> ScopeTarget:
        return ScopeTarget(require_tenant().id, self.institution_id, self.campus_id)

    def filters(self) -> dict[str, object]:
        return {
            "scope_type": self.kind,
            "institution_id": self.institution_id,
            "campus_id": self.campus_id,
        }

    def cache_part(self) -> str:
        return f"{self.institution_id or '-'}.{self.campus_id or '-'}"


TENANT_SCOPE = ConfigScope()
