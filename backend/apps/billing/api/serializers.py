"""Serializers of the billing API (Phase 4 M5; plan §6). Prices are owner data: the API
validates and stores what the owner enters and never suggests amounts (ADR-024)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.billing.models import AddOn, Plan, Price
from apps.tenancy.api.serializers import LimitUsageSerializer

REASON = serializers.CharField(min_length=10, max_length=200)


class PlanSerializer(serializers.Serializer[Any]):
    code = serializers.CharField()
    name = serializers.CharField()
    name_i18n = serializers.DictField(child=serializers.CharField())
    is_public = serializers.BooleanField()
    limits = serializers.DictField(child=serializers.IntegerField())
    trial_days = serializers.IntegerField(allow_null=True)
    archived = serializers.BooleanField()
    modules = serializers.ListField(child=serializers.CharField())

    @staticmethod
    def of(plan: Plan) -> dict[str, Any]:
        return {
            "code": plan.code,
            "name": plan.name,
            "name_i18n": plan.name_i18n or {},
            "is_public": plan.is_public,
            "limits": plan.limits or {},
            "trial_days": plan.trial_days,
            "archived": plan.archived_at is not None,
            "modules": sorted(
                str(c) for c in plan.plan_modules.values_list("module__code", flat=True)
            ),
        }


class PlanCreateSerializer(serializers.Serializer[Any]):
    code = serializers.RegexField(r"^[a-z][a-z0-9_]{1,39}$")
    name = serializers.CharField(max_length=120)
    limits = serializers.DictField(child=serializers.IntegerField(min_value=1), required=False)
    modules = serializers.ListField(child=serializers.CharField(max_length=64), required=False)
    is_public = serializers.BooleanField(required=False, default=False)
    trial_days = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=365
    )


class PlanUpdateSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=120, required=False)
    name_i18n = serializers.DictField(child=serializers.CharField(max_length=120), required=False)
    is_public = serializers.BooleanField(required=False)
    limits = serializers.DictField(child=serializers.IntegerField(min_value=1), required=False)
    trial_days = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=365
    )
    archived = serializers.BooleanField(required=False)
    modules = serializers.ListField(child=serializers.CharField(max_length=64), required=False)


class AddOnSerializer(serializers.Serializer[Any]):
    code = serializers.CharField()
    name = serializers.CharField()
    module = serializers.CharField(allow_null=True)
    archived = serializers.BooleanField()

    @staticmethod
    def of(addon: AddOn) -> dict[str, Any]:
        return {
            "code": addon.code,
            "name": addon.name,
            "module": addon.module_id,
            "archived": addon.archived_at is not None,
        }


class AddOnCreateSerializer(serializers.Serializer[Any]):
    code = serializers.RegexField(r"^[a-z][a-z0-9_]{1,39}$")
    name = serializers.CharField(max_length=120)
    module = serializers.CharField(max_length=64, allow_null=True, required=False)


class PriceSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    plan = serializers.CharField(allow_null=True)
    addon = serializers.CharField(allow_null=True)
    currency = serializers.CharField()
    interval = serializers.CharField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    active = serializers.BooleanField()
    created_at = serializers.DateTimeField()

    @staticmethod
    def of(price: Price) -> dict[str, Any]:
        return {
            "id": price.pk,
            "plan": price.plan.code if price.plan is not None else None,
            "addon": price.addon.code if price.addon is not None else None,
            "currency": price.currency,
            "interval": price.interval,
            "amount": price.amount,
            "active": price.active,
            "created_at": price.created_at,
        }


class PriceCreateSerializer(serializers.Serializer[Any]):
    plan = serializers.CharField(max_length=40, required=False, allow_null=True)
    addon = serializers.CharField(max_length=40, required=False, allow_null=True)
    currency = serializers.RegexField(r"^[A-Z]{3}$")
    interval = serializers.ChoiceField(choices=Price.Interval.choices)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=0)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if bool(attrs.get("plan")) == bool(attrs.get("addon")):
            raise serializers.ValidationError("Give exactly one of plan or addon.")
        return attrs


class ModuleStateSerializer(serializers.Serializer[Any]):
    code = serializers.CharField()
    # The metaclass collects declared fields, so a field named "source" is fine at runtime.
    source = serializers.CharField()  # type: ignore[assignment]
    enabled = serializers.BooleanField()
    reason = serializers.CharField()


class SubscribedAddOnSerializer(serializers.Serializer[Any]):
    code = serializers.CharField()
    name = serializers.CharField()
    valid_from = serializers.DateTimeField()
    valid_until = serializers.DateTimeField(allow_null=True)


class OverrideSerializer(serializers.Serializer[Any]):
    module = serializers.CharField()
    kind = serializers.CharField()
    reason = serializers.CharField()
    expires_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class PlanRefSerializer(serializers.Serializer[Any]):
    code = serializers.CharField()
    name = serializers.CharField()


class SubscriptionSerializer(serializers.Serializer[Any]):
    tenant_id = serializers.UUIDField()
    plan = PlanRefSerializer(allow_null=True)
    status = serializers.CharField(allow_null=True)
    trial_ends_at = serializers.DateTimeField(allow_null=True)
    current_period_end = serializers.DateTimeField(allow_null=True)
    addons = SubscribedAddOnSerializer(many=True)
    overrides = OverrideSerializer(many=True)
    modules = ModuleStateSerializer(many=True)


class TenantSubscriptionSerializer(serializers.Serializer[Any]):
    plan = PlanRefSerializer(allow_null=True)
    status = serializers.CharField(allow_null=True)
    trial_ends_at = serializers.DateTimeField(allow_null=True)
    current_period_end = serializers.DateTimeField(allow_null=True)
    addons = SubscribedAddOnSerializer(many=True)
    modules = ModuleStateSerializer(many=True)
    limits = serializers.DictField(child=LimitUsageSerializer())


class ChangeReasonSerializer(serializers.Serializer[Any]):
    reason = REASON


class AssignPlanSerializer(serializers.Serializer[Any]):
    plan = serializers.CharField(max_length=40)
    reason = REASON


class TrialSerializer(serializers.Serializer[Any]):
    plan = serializers.CharField(max_length=40)
    days = serializers.IntegerField(min_value=1, max_value=365)
    reason = REASON


class AddAddOnSerializer(serializers.Serializer[Any]):
    addon = serializers.CharField(max_length=40)
    valid_until = serializers.DateTimeField(required=False, allow_null=True)
    reason = REASON


class SetOverrideSerializer(serializers.Serializer[Any]):
    module = serializers.CharField(max_length=64)
    kind = serializers.ChoiceField(choices=["grant", "revoke"])
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    reason = REASON
