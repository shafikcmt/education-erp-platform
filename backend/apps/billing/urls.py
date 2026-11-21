"""Billing routes (Phase 4 M5)."""

from django.urls import path

from apps.billing.api import views as v

app_name = "billing"

urlpatterns = [
    path("platform/plans/", v.PlansView.as_view(), name="platform-plans"),
    path("platform/plans/<str:code>/", v.PlanDetailView.as_view(), name="platform-plan"),
    path("platform/addons/", v.AddOnsView.as_view(), name="platform-addons"),
    path("platform/prices/", v.PricesView.as_view(), name="platform-prices"),
    path(
        "platform/prices/<str:price_id>/deactivate/",
        v.PriceDeactivateView.as_view(),
        name="platform-price-deactivate",
    ),
    path(
        "platform/tenants/<str:tenant_id>/subscription/",
        v.TenantSubscriptionAdminView.as_view(),
        name="platform-subscription",
    ),
    path(
        "platform/tenants/<str:tenant_id>/subscription/plan/",
        v.SubscriptionPlanView.as_view(),
        name="platform-subscription-plan",
    ),
    path(
        "platform/tenants/<str:tenant_id>/subscription/trial/",
        v.SubscriptionTrialView.as_view(),
        name="platform-subscription-trial",
    ),
    path(
        "platform/tenants/<str:tenant_id>/subscription/addons/",
        v.SubscriptionAddOnsView.as_view(),
        name="platform-subscription-addons",
    ),
    path(
        "platform/tenants/<str:tenant_id>/subscription/addons/<str:code>/remove/",
        v.SubscriptionAddOnRemoveView.as_view(),
        name="platform-subscription-addon-remove",
    ),
    path(
        "platform/tenants/<str:tenant_id>/subscription/overrides/",
        v.SubscriptionOverridesView.as_view(),
        name="platform-subscription-overrides",
    ),
    path(
        "platform/tenants/<str:tenant_id>/subscription/overrides/<str:module>/end/",
        v.SubscriptionOverrideEndView.as_view(),
        name="platform-subscription-override-end",
    ),
    path("tenant/subscription/", v.OwnSubscriptionView.as_view(), name="tenant-subscription"),
]
