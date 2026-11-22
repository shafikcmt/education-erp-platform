"""Configuration versions and the effective config resolver (Phase 5 M1; ADR-057)."""

from __future__ import annotations

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.db.utils import IntegrityError

from apps.core.tenancy import tenant_atomic
from apps.customization import services
from apps.customization.models import ConfigVersion
from apps.customization.registry import (
    InvalidSettingsCatalogError,
    _spec,
    declared_settings,
)
from apps.customization.resolver import effective_config, get_effective_config
from apps.customization.scopes import ConfigScope
from tests.helpers import make_user
from tests.isolation.factories import grant_role, seed_tenant_roles, tenant_events

pytestmark = pytest.mark.django_db
TENANT = ConfigScope()


@pytest.fixture
def owner(org):
    user = make_user("studio-owner@example.com", mfa=True).user
    grant_role(org.tenant, user, "tenant_owner")
    return user


def _publish(actor, scope, data, note=""):
    services.save_draft(actor=actor, scope=scope, data=data)
    return services.publish(actor=actor, scope=scope, note=note)


def test_the_catalogue_validates_its_declarations():
    specs = declared_settings()
    assert {"customization.terminology", "tenancy.week_start"} <= set(specs)
    good = {"schema": {"type": "integer"}, "default": 1, "scopes": ["tenant"]}
    with pytest.raises(InvalidSettingsCatalogError, match="keys are"):
        _spec("tenancy", "billing.thing", good)
    with pytest.raises(InvalidSettingsCatalogError, match="default does not validate"):
        _spec("tenancy", "tenancy.thing", {**good, "default": "x"})
    with pytest.raises(InvalidSettingsCatalogError, match="scopes"):
        _spec("tenancy", "tenancy.thing", {**good, "scopes": ["planet"]})
    with pytest.raises(InvalidSettingsCatalogError, match="deep"):
        _spec("tenancy", "tenancy.thing", {**good, "merge": "deep"})


def test_defaults_then_tenant_institution_campus(org, owner):
    with tenant_atomic(org.tenant):
        campus = ConfigScope(org.north.pk, org.main.pk)
        assert get_effective_config(campus, "tenancy.week_start") == 1
        _publish(owner, TENANT, {"tenancy.week_start": 6})
        _publish(owner, ConfigScope(org.north.pk), {"tenancy.week_start": 7})
        assert get_effective_config(TENANT, "tenancy.week_start") == 6
        assert get_effective_config(ConfigScope(org.south.pk), "tenancy.week_start") == 6
        assert get_effective_config(campus, "tenancy.week_start") == 7
        _publish(owner, campus, {"tenancy.week_start": 5})
        assert get_effective_config(campus, "tenancy.week_start") == 5
        assert (
            get_effective_config(ConfigScope(org.north.pk, org.annex.pk), "tenancy.week_start") == 7
        )
        with pytest.raises(KeyError):
            get_effective_config(TENANT, "tenancy.nope")


def test_terminology_merges_deeply_across_scopes(org, owner):
    with tenant_atomic(org.tenant):
        _publish(
            owner,
            TENANT,
            {
                "customization.terminology": {
                    "en": {"unit.section": "Section", "unit.class": "Class"}
                }
            },
        )
        _publish(
            owner,
            ConfigScope(org.south.pk),
            {
                "customization.terminology": {
                    "en": {"unit.section": "Jamaat"},
                    "bn": {"unit.section": "জামাত"},
                }
            },
        )
        merged = get_effective_config(ConfigScope(org.south.pk), "customization.terminology")
        assert merged == {
            "en": {"unit.section": "Jamaat", "unit.class": "Class"},
            "bn": {"unit.section": "জামাত"},
        }
        assert (
            get_effective_config(TENANT, "customization.terminology")["en"]["unit.section"]
            == "Section"
        )


def test_validation_rejects_unknown_keys_bad_values_and_wrong_scopes(org, owner):
    with tenant_atomic(org.tenant):
        cases: list[tuple[dict, str]] = [
            ({"tenancy.nope": 1}, "Unknown setting"),
            ({"tenancy.week_start": 9}, "Invalid value"),
            ({"tenancy.week_start": "1"}, "Invalid value"),
            ({"customization.terminology": {"en": {"BAD KEY": "x"}}}, "Invalid value"),
        ]
        for data, message in cases:
            with pytest.raises(ValidationError, match=message):
                services.save_draft(actor=owner, scope=TENANT, data=data)
        campus = ConfigScope(org.north.pk, org.main.pk)
        with pytest.raises(ValidationError, match="can't be set for a campus"):
            services.save_draft(
                actor=owner, scope=campus, data={"tenancy.academic_year_start_month": 7}
            )
        with pytest.raises(ValidationError, match="too large"):
            services.save_draft(
                actor=owner,
                scope=TENANT,
                data={"customization.terminology": {"en": {f"k{i}": "x" * 80 for i in range(900)}}},
            )


def test_drafts_are_invisible_until_published_and_published_versions_are_immutable(org, owner):
    with tenant_atomic(org.tenant):
        _publish(owner, TENANT, {"tenancy.week_start": 6})
        draft = services.save_draft(actor=owner, scope=TENANT, data={"tenancy.week_start": 3})
        assert get_effective_config(TENANT, "tenancy.week_start") == 6  # draft not served
        assert draft.number == 2 and draft.status == "draft"
        services.save_draft(actor=owner, scope=TENANT, data={"tenancy.week_start": 4})
        assert ConfigVersion.objects.filter(status="draft").count() == 1  # one draft per scope
        assert services.discard_draft(actor=owner, scope=TENANT) is True
        assert services.discard_draft(actor=owner, scope=TENANT) is False
        with pytest.raises(ValidationError, match="no draft"):
            services.publish(actor=owner, scope=TENANT)


def test_publish_archives_and_rollback_publishes_a_copy(org, owner):
    with tenant_atomic(org.tenant):
        v1 = _publish(owner, TENANT, {"tenancy.week_start": 6}, note="first")
        v2 = _publish(owner, TENANT, {"tenancy.week_start": 7})
        v1.refresh_from_db()
        assert (v1.status, v2.status) == ("archived", "published")
        assert get_effective_config(TENANT, "tenancy.week_start") == 7
        v3 = services.rollback(actor=owner, scope=TENANT, number=1)
        assert (v3.number, v3.status, v3.based_on, v3.data) == (
            3,
            "published",
            1,
            {"tenancy.week_start": 6},
        )
        assert get_effective_config(TENANT, "tenancy.week_start") == 6
        assert ConfigVersion.objects.filter(status="published").count() == 1
        with pytest.raises(ValidationError, match="Unknown published"):
            services.rollback(actor=owner, scope=TENANT, number=99)
    actions = [e.action for e in tenant_events(org.tenant) if e.action.startswith("customization.")]
    assert actions.count("customization.config.published") == 2
    assert actions.count("customization.config.rolled_back") == 1
    [rolled] = tenant_events(org.tenant, action="customization.config.rolled_back")
    assert rolled.metadata == {
        "scope": "tenant",
        "number": 3,
        "source": 1,
        "added": [],
        "removed": [],
        "changed": ["tenancy.week_start"],
    }


def test_permissions_are_checked_in_the_exact_scope(org, owner):
    head = make_user("head-studio@example.com", mfa=True).user
    grant_role(org.tenant, head, "institution_admin", institution=org.north)
    teacher = make_user("teacher-studio@example.com").user
    grant_role(org.tenant, teacher, "teacher", institution=org.north, campus=org.main)
    with tenant_atomic(org.tenant):
        _publish(head, ConfigScope(org.north.pk), {"tenancy.week_start": 7})
        _publish(head, ConfigScope(org.north.pk, org.main.pk), {"tenancy.week_start": 6})
        for scope in (TENANT, ConfigScope(org.south.pk)):
            with pytest.raises(PermissionDenied):
                services.save_draft(actor=head, scope=scope, data={"tenancy.week_start": 2})
        with pytest.raises(PermissionDenied):
            services.save_draft(actor=teacher, scope=ConfigScope(org.north.pk), data={})
        with pytest.raises(ValidationError, match="Unknown campus"):
            services.save_draft(actor=owner, scope=ConfigScope(org.south.pk, org.main.pk), data={})


def test_cache_is_invalidated_by_publish(org, owner):
    with tenant_atomic(org.tenant):
        assert effective_config(TENANT)["tenancy.week_start"] == 1  # cached now
        _publish(owner, TENANT, {"tenancy.week_start": 2})
        assert effective_config(TENANT)["tenancy.week_start"] == 2


def test_versions_are_tenant_isolated_and_keys_composite(org, owner, tenant_site):
    other = tenant_site(slug="bravo")
    seed_tenant_roles(other)
    with tenant_atomic(org.tenant):
        _publish(owner, TENANT, {"tenancy.week_start": 6})
    with tenant_atomic(other):
        assert ConfigVersion.objects.count() == 0
        assert get_effective_config(TENANT, "tenancy.week_start") == 1
        with connection.cursor() as cursor:  # raw SQL as erp_app: RLS, not the manager
            cursor.execute(
                "SELECT count(*) FROM customization_configversion WHERE tenant_id = %s",
                [org.tenant.id],
            )
            assert cursor.fetchone() == (0,)
        # A version of this tenant can't reference the other tenant's institution.
        with pytest.raises(IntegrityError):
            ConfigVersion.objects.create(
                scope_type="institution", institution_id=org.north.pk, number=1
            )
