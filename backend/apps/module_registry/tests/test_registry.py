"""Module catalogue (Phase 4 M1; ADR-050): manifests, validation, owner-only sync."""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.utils import ProgrammingError

from apps.module_registry import catalog
from apps.module_registry.models import Module
from apps.module_registry.registry import (
    InvalidModuleCatalog,
    _assert_acyclic,
    _spec,
    declared_modules,
    dependency_closure,
)
from apps.module_registry.sync import catalog_drift, sync_modules

pytestmark = pytest.mark.django_db

# CLAUDE.md §5: every canonical module code is in the catalogue.
CANONICAL = {
    "core", "tenancy", "identity", "rbac", "module_registry", "billing", "customization",
    "audit", "files", "notifications_core", "academics", "timetable", "admissions", "students",
    "staff", "parent_portal", "attendance", "examinations", "fees", "accounting", "hr_payroll",
    "hostel", "transport", "library", "lms", "online_exams", "communication",
    "reports_analytics", "ai_assistant", "custom_module_builder",
}  # fmt: skip


def test_catalogue_covers_every_canonical_module_and_marks_installed_ones():
    specs = declared_modules()
    assert set(specs) >= CANONICAL
    installed = {c for c, s in specs.items() if s.available}
    assert installed == {
        "core", "identity", "rbac", "audit", "tenancy", "module_registry", "billing",
        "customization", "notifications_core", "academics", "files", "admissions", "students",
        "staff", "timetable",
    }  # fmt: skip
    assert all(not s.sellable for s in specs.values() if s.category == "platform")
    assert specs["hostel"].dependencies == ("students", "fees", "attendance")


def test_database_matches_the_declared_catalogue():
    """The test bootstrap ran ``sync_modules`` as the owner (as the compose migrate step)."""
    assert catalog_drift() == []
    assert Module.objects.get(code="tenancy").available is True
    assert Module.objects.get(code="hostel").available is False


def test_dependency_closure_is_transitive():
    specs = declared_modules()
    closure = dependency_closure({"hostel"}, specs)
    assert {"hostel", "students", "fees", "attendance", "staff", "academics"} <= closure
    assert "customization" in closure  # academics -> customization
    assert dependency_closure({"no_such_module"}, specs) == set()


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"code": "Bad", "category": "standard", "version": "1.0.0"}, "Invalid module code"),
        ({"code": "x_mod", "category": "other", "version": "1.0.0"}, "unknown category"),
        ({"code": "x_mod", "category": "standard", "version": "1"}, "MAJOR.MINOR.PATCH"),
        (
            {"code": "x_mod", "category": "platform", "version": "1.0.0", "sellable": True},
            "never sold",
        ),
        (
            {
                "code": "x_mod",
                "category": "standard",
                "version": "1.0.0",
                "dependencies": ["x_mod"],
            },
            "itself",
        ),
    ],
)
def test_invalid_manifests_are_refused(raw, message):
    with pytest.raises(InvalidModuleCatalog, match=message):
        _spec(raw, available=False)


def test_cycles_and_unknown_dependencies_are_refused(monkeypatch):
    a = _spec(
        {"code": "aa", "category": "standard", "version": "1.0.0", "dependencies": ["bb"]},
        available=False,
    )
    b = _spec(
        {"code": "bb", "category": "standard", "version": "1.0.0", "dependencies": ["aa"]},
        available=False,
    )
    with pytest.raises(InvalidModuleCatalog, match="cycle"):
        _assert_acyclic({"aa": a, "bb": b})
    broken = [
        *catalog.PLANNED_MODULES,
        {"code": "zz", "category": "standard", "version": "1.0.0", "dependencies": ["nope"]},
    ]
    monkeypatch.setattr("apps.module_registry.registry.PLANNED_MODULES", broken)
    with pytest.raises(InvalidModuleCatalog, match="unknown dependencies"):
        declared_modules()


def test_runtime_role_can_only_read_the_module_catalogue():
    assert Module.objects.exists()
    with pytest.raises(ProgrammingError, match="permission denied"), connection.cursor() as cursor:
        cursor.execute("UPDATE module_registry_module SET name = 'x' WHERE code = 'core'")


def test_sync_refuses_the_runtime_role():
    with pytest.raises(CommandError, match="owner role"):
        sync_modules()
    with pytest.raises(CommandError, match="owner role"):
        call_command("sync_modules")
