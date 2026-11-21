"""Module registry routes (Phase 4 M5)."""

from django.urls import path

from apps.module_registry.api import views as v

app_name = "module_registry"

urlpatterns = [
    path("platform/modules/", v.ModulesView.as_view(), name="platform-modules"),
    path("platform/feature-flags/", v.FeatureFlagsView.as_view(), name="platform-feature-flags"),
]
