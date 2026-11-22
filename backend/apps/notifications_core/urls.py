"""Notification routes (Phase 5 M6)."""

from django.urls import path

from apps.notifications_core import api

app_name = "notifications_core"

urlpatterns = [
    path("notifications/", api.InboxView.as_view(), name="inbox"),
    path("notifications/read/", api.MarkReadView.as_view(), name="read"),
]
