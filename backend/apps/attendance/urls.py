"""Attendance routes (Phase 8 M2). Tenant host only."""

from django.urls import path

from apps.attendance.api import views as v

app_name = "attendance"

urlpatterns = [
    path("attendance/due/", v.DueView.as_view(), name="due"),
    path("attendance/registers/", v.RegistersView.as_view(), name="registers"),
    path("attendance/registers/<str:register_id>/", v.RegisterView.as_view(), name="register"),
    path(
        "attendance/registers/<str:register_id>/save/",
        v.RegisterSaveView.as_view(),
        name="register-save",
    ),
    path(
        "attendance/registers/<str:register_id>/submit/",
        v.RegisterSubmitView.as_view(),
        name="register-submit",
    ),
    path(
        "attendance/registers/<str:register_id>/unlock/",
        v.RegisterUnlockView.as_view(),
        name="register-unlock",
    ),
]
