"""Billing API (Phase 4 M5; plan §6; ADR-051, ADR-054).

Platform host: the catalogue (plans, add-ons, prices; P17) and one tenant's subscription
(plan, trial, add-ons, module overrides; P18). Reads list registry rows only (no tenant-owned
data); every write calls a service that runs the catalogued operation inside
``platform_scope`` and checks the permission again, uncached. Price and subscription changes
need a fresh step-up (permission flags).

Tenant host: ``/tenant/subscription/`` (read-only, ``billing.subscription.view``).
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from apps.billing import selectors, services
from apps.billing.api import serializers as s
from apps.billing.models import AddOn, Plan, Price
from apps.core.hosts import TENANT_ONLY
from apps.core.tenancy import require_tenant
from apps.identity.api.utils import CsrfProtectedView, get_or_404, service_errors
from apps.identity.models import User
from apps.module_registry import services as registry_services
from apps.module_registry.permissions import ModuleGatedView
from apps.rbac.permissions import HasPermission
from apps.tenancy.models import Tenant
from apps.tenancy.rules import TenantStatus

TAGS = ["platform-billing"]
VIEW, MANAGE = "billing.plan.view", "billing.plan.manage"
SUB_VIEW, SUB_MANAGE = "billing.subscription.view_any", "billing.subscription.manage"


def _actor(request: Request) -> User:
    assert isinstance(request.user, User)  # noqa: S101 - permission classes guarantee it
    return request.user


def _valid(serializer_class: Any, request: Request) -> dict[str, Any]:
    data = serializer_class(data=request.data)
    data.is_valid(raise_exception=True)
    return dict(data.validated_data)


def _plan(code: str) -> Plan:
    plan = Plan.objects.filter(code=code[:40]).first()
    if plan is None:
        raise NotFound()
    return plan


def _tenant_id(tenant_id: str) -> Any:
    tenant = get_or_404(Tenant.objects.exclude(status=TenantStatus.DELETED), tenant_id)
    return tenant.pk


# --------------------------------------------------------------------------- catalogue (P17)
class PlansView(CsrfProtectedView):
    permission_classes = [HasPermission({"GET": VIEW, "POST": MANAGE})]
    platform_operations = {"GET": "P17", "POST": "P17"}

    @extend_schema(tags=TAGS, summary="Plans", responses=s.PlanSerializer(many=True))
    def get(self, request: Request) -> Response:
        plans = Plan.objects.order_by("code")
        return Response(s.PlanSerializer([s.PlanSerializer.of(p) for p in plans], many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Create a plan (no prices: those are entered separately)",
        request=s.PlanCreateSerializer,
        responses={201: s.PlanSerializer},
    )
    def post(self, request: Request) -> Response:
        values = _valid(s.PlanCreateSerializer, request)
        with service_errors():
            plan = services.create_plan(actor=_actor(request), request=request, **values)
        return Response(s.PlanSerializer(s.PlanSerializer.of(plan)).data, status.HTTP_201_CREATED)


class PlanDetailView(CsrfProtectedView):
    permission_classes = [HasPermission({"GET": VIEW, "PATCH": MANAGE})]
    platform_operations = {"GET": "P17", "PATCH": "P17"}

    @extend_schema(tags=TAGS, summary="Plan", responses=s.PlanSerializer)
    def get(self, request: Request, code: str) -> Response:
        return Response(s.PlanSerializer(s.PlanSerializer.of(_plan(code))).data)

    @extend_schema(
        tags=TAGS,
        summary="Update a plan (name, visibility, limits, trial length, modules, archive)",
        request=s.PlanUpdateSerializer,
        responses=s.PlanSerializer,
    )
    def patch(self, request: Request, code: str) -> Response:
        values = _valid(s.PlanUpdateSerializer, request)
        modules = values.pop("modules", None)
        with service_errors():
            plan = services.update_plan(
                actor=_actor(request),
                plan=_plan(code),
                changes=values,
                modules=modules,
                request=request,
            )
        return Response(s.PlanSerializer(s.PlanSerializer.of(plan)).data)


class AddOnsView(CsrfProtectedView):
    permission_classes = [HasPermission({"GET": VIEW, "POST": MANAGE})]
    platform_operations = {"GET": "P17", "POST": "P17"}

    @extend_schema(tags=TAGS, summary="Add-ons", responses=s.AddOnSerializer(many=True))
    def get(self, request: Request) -> Response:
        rows = AddOn.objects.order_by("code")
        return Response(s.AddOnSerializer([s.AddOnSerializer.of(a) for a in rows], many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Create an add-on for a sellable module",
        request=s.AddOnCreateSerializer,
        responses={201: s.AddOnSerializer},
    )
    def post(self, request: Request) -> Response:
        values = _valid(s.AddOnCreateSerializer, request)
        with service_errors():
            addon = services.create_addon(
                actor=_actor(request),
                code=values["code"],
                name=values["name"],
                module=values.get("module"),
                request=request,
            )
        return Response(
            s.AddOnSerializer(s.AddOnSerializer.of(addon)).data, status.HTTP_201_CREATED
        )


class PricesView(CsrfProtectedView):
    permission_classes = [HasPermission({"GET": VIEW, "POST": "billing.price.manage"})]
    platform_operations = {"GET": "P17", "POST": "P17"}

    @extend_schema(
        tags=TAGS,
        summary="Prices (owner-entered data)",
        parameters=[
            OpenApiParameter("plan", OpenApiTypes.STR),
            OpenApiParameter("addon", OpenApiTypes.STR),
            OpenApiParameter("active", OpenApiTypes.BOOL),
        ],
        responses=s.PriceSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        rows = Price.objects.select_related("plan", "addon").order_by("-created_at")
        if value := request.query_params.get("plan"):
            rows = rows.filter(plan__code=value[:40])
        if value := request.query_params.get("addon"):
            rows = rows.filter(addon__code=value[:40])
        if request.query_params.get("active") in ("true", "1"):
            rows = rows.filter(active=True)
        return Response(s.PriceSerializer([s.PriceSerializer.of(p) for p in rows], many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Add a price (replaces the active one for the same target, currency, interval)",
        request=s.PriceCreateSerializer,
        responses={201: s.PriceSerializer},
    )
    def post(self, request: Request) -> Response:
        values = _valid(s.PriceCreateSerializer, request)
        plan = _plan(values["plan"]) if values.get("plan") else None
        addon = None
        if values.get("addon"):
            addon = AddOn.objects.filter(code=values["addon"][:40]).first()
            if addon is None:
                raise NotFound()
        with service_errors():
            price = services.add_price(
                actor=_actor(request),
                plan=plan,
                addon=addon,
                currency=values["currency"],
                interval=values["interval"],
                amount=values["amount"],
                request=request,
            )
        price = Price.objects.select_related("plan", "addon").get(pk=price.pk)
        return Response(
            s.PriceSerializer(s.PriceSerializer.of(price)).data, status.HTTP_201_CREATED
        )


class PriceDeactivateView(CsrfProtectedView):
    permission_classes = [HasPermission({"POST": "billing.price.manage"})]
    platform_operations = {"POST": "P17"}

    @extend_schema(
        tags=TAGS, summary="Deactivate a price", request=None, responses=s.PriceSerializer
    )
    def post(self, request: Request, price_id: str) -> Response:
        price = get_or_404(Price.objects.select_related("plan", "addon"), price_id)
        with service_errors():
            price = services.deactivate_price(actor=_actor(request), price=price, request=request)
        return Response(s.PriceSerializer(s.PriceSerializer.of(price)).data)


# --------------------------------------------------------------------------- subscription (P18)
SUB_TAGS = ["platform-tenants"]


def _detail(tenant_id: Any) -> Response:
    return Response(s.SubscriptionSerializer(selectors.subscription_detail(tenant_id)).data)


class TenantSubscriptionAdminView(CsrfProtectedView):
    permission_classes = [HasPermission({"GET": SUB_VIEW})]
    platform_operations = {"GET": "P18"}

    @extend_schema(
        tags=SUB_TAGS,
        summary="A tenant's plan, add-ons, overrides and resolved modules",
        responses=s.SubscriptionSerializer,
    )
    def get(self, request: Request, tenant_id: str) -> Response:
        return _detail(_tenant_id(tenant_id))


class SubscriptionPlanView(CsrfProtectedView):
    permission_classes = [HasPermission({"POST": SUB_MANAGE})]
    platform_operations = {"POST": "P18"}

    @extend_schema(
        tags=SUB_TAGS,
        summary="Assign a plan (ends a trial)",
        request=s.AssignPlanSerializer,
        responses=s.SubscriptionSerializer,
    )
    def post(self, request: Request, tenant_id: str) -> Response:
        values = _valid(s.AssignPlanSerializer, request)
        tid = _tenant_id(tenant_id)
        with service_errors():
            services.assign_plan(
                actor=_actor(request),
                tenant_id=tid,
                plan_code=values["plan"],
                reason=values["reason"],
                request=request,
            )
        return _detail(tid)


class SubscriptionTrialView(CsrfProtectedView):
    permission_classes = [HasPermission({"POST": SUB_MANAGE})]
    platform_operations = {"POST": "P18"}

    @extend_schema(
        tags=SUB_TAGS,
        summary="Start or extend a trial on a plan",
        request=s.TrialSerializer,
        responses=s.SubscriptionSerializer,
    )
    def post(self, request: Request, tenant_id: str) -> Response:
        values = _valid(s.TrialSerializer, request)
        tid = _tenant_id(tenant_id)
        with service_errors():
            services.start_trial(
                actor=_actor(request),
                tenant_id=tid,
                plan_code=values["plan"],
                days=values["days"],
                reason=values["reason"],
                request=request,
            )
        return _detail(tid)


class SubscriptionAddOnsView(CsrfProtectedView):
    permission_classes = [HasPermission({"POST": SUB_MANAGE})]
    platform_operations = {"POST": "P18"}

    @extend_schema(
        tags=SUB_TAGS,
        summary="Add an add-on",
        request=s.AddAddOnSerializer,
        responses=s.SubscriptionSerializer,
    )
    def post(self, request: Request, tenant_id: str) -> Response:
        values = _valid(s.AddAddOnSerializer, request)
        tid = _tenant_id(tenant_id)
        with service_errors():
            services.add_addon(
                actor=_actor(request),
                tenant_id=tid,
                addon_code=values["addon"],
                valid_until=values.get("valid_until"),
                reason=values["reason"],
                request=request,
            )
        return _detail(tid)


class SubscriptionAddOnRemoveView(CsrfProtectedView):
    permission_classes = [HasPermission({"POST": SUB_MANAGE})]
    platform_operations = {"POST": "P18"}

    @extend_schema(
        tags=SUB_TAGS,
        summary="Remove an add-on",
        request=s.ChangeReasonSerializer,
        responses=s.SubscriptionSerializer,
    )
    def post(self, request: Request, tenant_id: str, code: str) -> Response:
        values = _valid(s.ChangeReasonSerializer, request)
        tid = _tenant_id(tenant_id)
        with service_errors():
            removed = services.remove_addon(
                actor=_actor(request),
                tenant_id=tid,
                addon_code=code[:40],
                reason=values["reason"],
                request=request,
            )
        if not removed:
            raise NotFound()
        return _detail(tid)


class SubscriptionOverridesView(CsrfProtectedView):
    permission_classes = [HasPermission({"POST": SUB_MANAGE})]
    platform_operations = {"POST": "P18"}

    @extend_schema(
        tags=SUB_TAGS,
        summary="Grant or revoke one module for this tenant",
        request=s.SetOverrideSerializer,
        responses=s.SubscriptionSerializer,
    )
    def post(self, request: Request, tenant_id: str) -> Response:
        values = _valid(s.SetOverrideSerializer, request)
        tid = _tenant_id(tenant_id)
        with service_errors():
            registry_services.set_override(
                actor=_actor(request),
                tenant_id=tid,
                module_code=values["module"],
                kind=values["kind"],
                expires_at=values.get("expires_at"),
                reason=values["reason"],
                request=request,
            )
        return _detail(tid)


class SubscriptionOverrideEndView(CsrfProtectedView):
    permission_classes = [HasPermission({"POST": SUB_MANAGE})]
    platform_operations = {"POST": "P18"}

    @extend_schema(
        tags=SUB_TAGS,
        summary="End the open override of one module",
        request=s.ChangeReasonSerializer,
        responses=s.SubscriptionSerializer,
    )
    def post(self, request: Request, tenant_id: str, module: str) -> Response:
        values = _valid(s.ChangeReasonSerializer, request)
        tid = _tenant_id(tenant_id)
        with service_errors():
            ended = registry_services.end_override(
                actor=_actor(request),
                tenant_id=tid,
                module_code=module[:64],
                reason=values["reason"],
                request=request,
            )
        if not ended:
            raise NotFound()
        return _detail(tid)


# --------------------------------------------------------------------------- tenant host
class OwnSubscriptionView(ModuleGatedView, CsrfProtectedView):
    host_classes = TENANT_ONLY
    module_code = "billing"
    # Not served in restricted owner mode: the reviewed D2 list (Phase 3) is unchanged.
    permission_classes = [HasPermission({"GET": "billing.subscription.view"})]

    @extend_schema(
        tags=["tenant"],
        summary="This organisation's plan, modules and limits (read-only)",
        responses=s.TenantSubscriptionSerializer,
    )
    def get(self, request: Request) -> Response:
        data = selectors.tenant_subscription(require_tenant().id)
        return Response(s.TenantSubscriptionSerializer(data).data)
