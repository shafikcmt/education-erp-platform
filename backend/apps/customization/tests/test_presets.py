"""Institution-type presets (Phase 5 M2; ADR-058): files, validation, pinning, preset layer."""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.utils import ProgrammingError

from apps.core.tenancy import tenant_atomic
from apps.customization.models import Preset
from apps.customization.presets_catalog import (
    TYPE_PREFIX,
    InvalidPresetError,
    file_presets,
    validate_preset,
)
from apps.customization.resolver import get_effective_config
from apps.customization.scopes import ConfigScope
from apps.customization.sync import sync_presets
from apps.tenancy.models import Institution

pytestmark = pytest.mark.django_db

GOOD = {
    "code": "school.test.v1",
    "institution_type": "school",
    "version": 1,
    "name": {"en": "Test"},
    "suggested_modules": ["academics"],
    "settings": {"customization.capabilities": {"academics.credit_based": False}},
}


def test_every_institution_type_has_exactly_one_valid_default_preset():
    presets = file_presets()
    assert len(presets) == 12  # v1 drafts (Phase 5) and v2 (Phase 6, ADR-063), both kept
    for itype in TYPE_PREFIX:
        of_type = [p for p in presets.values() if p["institution_type"] == itype]
        defaults = [p for p in of_type if p["default_for_type"]]
        assert [p["version"] for p in defaults] == [2], itype  # one default: the v2 preset
        terminology = defaults[0]["settings"]["customization.terminology"]
        assert {"en", "bn"} <= set(terminology), itype  # both launch languages
    for version in ("v1", "v2"):
        assert presets[f"university.credit.{version}"]["settings"]["customization.capabilities"][
            "academics.credit_based"
        ]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"code": "school.Test.v1"}, "code must be"),
        ({"code": "madrasa.test.v1"}, "code must be"),
        ({"version": 2}, "version must match"),
        ({"suggested_modules": ["tenancy"]}, "platform modules"),
        ({"suggested_modules": ["nope"]}, "unknown"),
        ({"settings": {"tenancy.week_start": 9}}, "invalid value"),
        ({"settings": {"customization.nope": 1}}, "not an institution setting"),
        ({"extra": 1}, "top-level"),
    ],
)
def test_invalid_presets_are_refused(change, message):
    with pytest.raises(InvalidPresetError, match=message):
        validate_preset({**GOOD, **change})


def test_runtime_role_can_only_read_presets():
    assert Preset.objects.count() == 12  # synced by the owner bootstrap (v1 and v2)
    with pytest.raises(ProgrammingError, match="permission denied"), connection.cursor() as cursor:
        cursor.execute("UPDATE customization_preset SET is_default = false")


def test_sync_refuses_the_runtime_role():
    with pytest.raises(CommandError, match="owner role"):
        sync_presets()
    with pytest.raises(CommandError, match="owner role"):
        call_command("sync_presets")


def test_new_institutions_pin_their_types_default_preset_and_inherit_its_settings(org, admin):
    from apps.tenancy.services.registry import override_limits

    override_limits(
        actor=admin.user,
        tenant_id=org.tenant.id,
        limits={"max_institutions": 5, "max_campuses": 10},
        reason="Room for the preset test institutions",
    )
    with tenant_atomic(org.tenant):
        north = Institution.objects.get(pk=org.north.pk)  # created directly: no pin
        assert north.preset_code == ""
    from tests.helpers import make_user
    from tests.isolation.factories import grant_role

    owner = make_user("preset-owner@example.com", mfa=True).user
    grant_role(org.tenant, owner, "tenant_owner")
    from apps.tenancy.services.structure import create_institution

    with tenant_atomic(org.tenant):
        uni = create_institution(actor=owner, code="uni", name="Uni", institution_type="university")
        madrasa = create_institution(
            actor=owner, code="mad", name="Mad", institution_type="madrasa"
        )
        assert (uni.preset_code, uni.preset_version) == ("university.credit.v2", "2")
        flags = get_effective_config(ConfigScope(uni.pk), "customization.capabilities")
        assert flags["academics.credit_based"] is True
        terms = get_effective_config(ConfigScope(madrasa.pk), "customization.terminology")
        assert terms["bn"]["unit.class"] == "জামাত"
        # The tenant scope has no preset; the tenant's own values still win over the preset.
        assert get_effective_config(ConfigScope(), "customization.terminology") == {}
        from apps.customization import services

        services.save_draft(
            actor=owner,
            scope=ConfigScope(madrasa.pk),
            data={"customization.terminology": {"en": {"unit.class": "Class"}}},
        )
        services.publish(actor=owner, scope=ConfigScope(madrasa.pk))
        terms = get_effective_config(ConfigScope(madrasa.pk), "customization.terminology")
        assert (terms["en"]["unit.class"], terms["bn"]["unit.class"]) == ("Class", "জামাত")
