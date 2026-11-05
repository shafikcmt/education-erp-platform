"""Core API routes (mounted under /api/v1/)."""

from django.urls import path

from apps.core.health import SystemHealthView

app_name = "core"

urlpatterns = [
    path("system/health/", SystemHealthView.as_view(), name="system-health"),
]
