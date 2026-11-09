"""``core.db.tenant_atomic``: the name ADR-009 §4 and CLAUDE.md §10 use for the single
sanctioned tenant-transaction helper.

The implementation lives in :mod:`apps.core.tenancy.transaction` (Phase 3 plan §8.1); this
module only re-exports that same function, so there is exactly one helper.
"""

from apps.core.tenancy.transaction import tenant_atomic

__all__ = ["tenant_atomic"]
