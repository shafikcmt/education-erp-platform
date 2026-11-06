"""audit routes, mounted under /api/v1/ (plan §8)."""

from django.urls import path

from apps.audit import api

app_name = "audit"

urlpatterns = [
    path("platform/audit-events/", api.AuditEventsView.as_view(), name="platform-audit-events"),
    path(
        "platform/audit-events/<str:event_id>/reveal-ip/",
        api.RevealIpView.as_view(),
        name="platform-audit-event-reveal-ip",
    ),
]
