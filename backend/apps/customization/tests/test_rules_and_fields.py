"""Rule definitions and custom fields (Phase 5 M3; ADR-055; CUSTOMIZATION_ENGINE.md §4.2)."""

from __future__ import annotations

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection

from apps.core.tenancy import tenant_atomic
from apps.customization import fields, rule_services
from apps.customization.models import FieldDefinition, RuleDefinition
from apps.customization.rules import RuleError
from tests.helpers import make_user
from tests.isolation.factories import grant_role, seed_tenant_roles, tenant_events

pytestmark = pytest.mark.django_db
NS = "customization.form_visibility"
ADULT = {">=": [{"var": "field.age"}, 18]}
CASES = [
    {"context": {"field.age": 20}, "expected": True},
    {"context": {"field.age": 10}, "expected": False},
]


@pytest.fixture
def owner(org):
    user = make_user("rules-owner@example.com", mfa=True).user
    grant_role(org.tenant, user, "tenant_owner")
    return user


def test_rules_are_checked_tested_and_published(org, owner):
    with tenant_atomic(org.tenant):
        with pytest.raises(ValidationError, match="not allowed"):
            rule_services.save_rule_draft(
                actor=owner, namespace_code=NS, key="adult", name="Adult", rule={"eval": ["x"]}
            )
        with pytest.raises(ValidationError, match="Unknown rule namespace"):
            rule_services.save_rule_draft(
                actor=owner, namespace_code="nope.ns", key="adult", name="Adult", rule=ADULT
            )
        draft = rule_services.save_rule_draft(
            actor=owner, namespace_code=NS, key="adult", name="Adult", rule=ADULT
        )
        with pytest.raises(ValidationError, match="at least one test case"):
            rule_services.publish_rule(actor=owner, key="adult")
        wrong = [{"context": {"field.age": 20}, "expected": False}]
        rule_services.save_rule_draft(
            actor=owner, namespace_code=NS, key="adult", name="Adult", rule=ADULT, test_cases=wrong
        )
        with pytest.raises(ValidationError, match="1 test case"):
            rule_services.publish_rule(actor=owner, key="adult")
        rule_services.save_rule_draft(
            actor=owner, namespace_code=NS, key="adult", name="Adult", rule=ADULT, test_cases=CASES
        )
        published = rule_services.publish_rule(actor=owner, key="adult")
        assert (published.pk, published.status, published.number) == (draft.pk, "published", 1)
        assert rule_services.evaluate_published("adult", NS, {"field.age": 30}) is True
        # A new draft is version 2; the published version keeps serving until it is published.
        v2 = rule_services.save_rule_draft(
            actor=owner,
            namespace_code=NS,
            key="adult",
            name="Adult (21)",
            rule={">=": [{"var": "field.age"}, 21]},
            test_cases=[{"context": {"field.age": 20}, "expected": False}],
        )
        assert v2.number == 2
        assert rule_services.evaluate_published("adult", NS, {"field.age": 20}) is True
        rule_services.publish_rule(actor=owner, key="adult")
        assert rule_services.evaluate_published("adult", NS, {"field.age": 20}) is False
        assert RuleDefinition.objects.get(number=1).status == "archived"
        with pytest.raises(ValidationError, match="keeps its namespace"):
            rule_services.save_rule_draft(
                actor=owner,
                namespace_code="customization.workflow_guard",
                key="adult",
                name="x",
                rule={"==": [1, 1]},
            )
        with pytest.raises(RuleError, match="No published rule"):
            rule_services.evaluate_published("ghost", NS, {})
    assert len(tenant_events(org.tenant, action="customization.rule.published")) == 2


def test_rules_need_the_studio_permissions(org, owner):
    teacher = make_user("rules-teacher@example.com").user
    grant_role(org.tenant, teacher, "teacher", institution=org.north, campus=org.main)
    with tenant_atomic(org.tenant):
        with pytest.raises(PermissionDenied):
            rule_services.save_rule_draft(
                actor=teacher, namespace_code=NS, key="adult", name="A", rule=ADULT
            )
        rule_services.save_rule_draft(
            actor=owner, namespace_code=NS, key="adult", name="A", rule=ADULT, test_cases=CASES
        )
        with pytest.raises(PermissionDenied):
            rule_services.publish_rule(actor=teacher, key="adult")


def _define(owner, **kw):
    base: dict = {"entity": "tenancy.member", "key": "blood_group", "field_type": "single_select"}
    base.update(kw)
    labels = base.pop("labels", {"en": "Blood group", "bn": "রক্তের গ্রুপ"})
    return fields.define_field(actor=owner, labels=labels, **base)


def test_custom_fields_are_defined_validated_and_immutable(org, owner):
    with tenant_atomic(org.tenant):
        with pytest.raises(ValidationError, match="doesn't accept"):
            _define(owner, entity="fees.invoice")  # fees declares no custom-field entity yet
        with pytest.raises(ValidationError, match="1-100 options"):
            _define(owner)
        blood = _define(
            owner,
            options=[
                {"value": "a_pos", "labels": {"en": "A+"}},
                {"value": "o_neg", "labels": {"en": "O-"}},
            ],
            pii=True,
        )
        fields.define_field(
            actor=owner,
            entity="tenancy.member",
            key="joined_on",
            field_type="date",
            labels={"en": "Joined on"},
            required=True,
        )
        fields.define_field(
            actor=owner,
            entity="tenancy.member",
            key="allowance",
            field_type="decimal",
            labels={"en": "Allowance"},
            validation={"min": 0, "max": 50000},
        )
        with pytest.raises(ValidationError, match="exists"):
            _define(owner, options=[{"value": "x", "labels": {"en": "X"}}])
        with pytest.raises(ValidationError, match="never change"):
            fields.update_field(actor=owner, field=blood, changes={"field_type": "text"})
        with pytest.raises(ValidationError, match="Unknown permission"):
            fields.update_field(actor=owner, field=blood, changes={"view_permission": "x.y.z"})
        fields.update_field(
            actor=owner, field=blood, changes={"view_permission": "tenancy.member.view"}
        )

        ok = {"blood_group": "a_pos", "joined_on": "2026-01-15", "allowance": "1200.50"}
        assert fields.validate_values("tenancy.member", ok) == ok
        bad = {
            "blood_group": "b_pos",
            "joined_on": "2026-02-30",
            "allowance": 12.5,  # a float: decimals are strings
            "nickname": "x",
        }
        with pytest.raises(ValidationError) as caught:
            fields.validate_values("tenancy.member", bad)
        assert set(caught.value.message_dict) == {
            "blood_group",
            "joined_on",
            "allowance",
            "nickname",
        }
        with pytest.raises(ValidationError, match="required"):
            fields.validate_values("tenancy.member", {"blood_group": "a_pos"})
        assert fields.validate_values("tenancy.member", {"blood_group": "a_pos"}, partial=True)
        with pytest.raises(ValidationError, match="Out of range"):
            fields.validate_values("tenancy.member", {**ok, "allowance": "99999"})

        fields.deprecate_field(actor=owner, field=blood)
        with pytest.raises(ValidationError, match="deprecated"):
            fields.validate_values("tenancy.member", ok)
        assert fields.validate_values(
            "tenancy.member", {"joined_on": "2026-01-15", "allowance": "1"}
        )
    actions = [
        e.action for e in tenant_events(org.tenant) if e.action.startswith("customization.field")
    ]
    assert actions.count("customization.field.defined") == 3
    assert "customization.field.deprecated" in actions


def test_definitions_are_tenant_isolated(org, owner, tenant_site):
    other = tenant_site(slug="bravo")
    seed_tenant_roles(other)
    with tenant_atomic(org.tenant):
        _define(owner, options=[{"value": "a", "labels": {"en": "A"}}])
        rule_services.save_rule_draft(
            actor=owner, namespace_code=NS, key="adult", name="A", rule=ADULT
        )
    with tenant_atomic(other):
        assert FieldDefinition.objects.count() == RuleDefinition.objects.count() == 0
        with pytest.raises(ValidationError, match="Unknown field"):
            fields.validate_values("tenancy.member", {"blood_group": "a"})
        with connection.cursor() as cursor:  # raw SQL as erp_app: RLS, not the manager
            for table in ("customization_fielddefinition", "customization_ruledefinition"):
                cursor.execute(
                    f"SELECT count(*) FROM {table} WHERE tenant_id = %s", [org.tenant.id]
                )
                assert cursor.fetchone() == (0,), table
