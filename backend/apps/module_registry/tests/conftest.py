"""Shared fixtures of the module registry tests (Phase 4)."""

from __future__ import annotations

import pytest

from apps.module_registry import entitlements
from apps.module_registry.models import Module

# Not-yet-built standard modules behave as built for these tests (the catalogue table is
# owner-written, so availability is patched in the resolver instead of the row).
BUILT = {"academics", "students", "fees", "attendance", "staff", "hostel", "customization"}


@pytest.fixture
def built(monkeypatch):
    real = entitlements._modules

    def patched() -> dict[str, Module]:
        modules = real()
        for code in BUILT & modules.keys():
            modules[code].available = True
        return modules

    monkeypatch.setattr(entitlements, "_modules", patched)
