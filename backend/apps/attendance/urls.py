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
    path("attendance/leave/", v.LeavesView.as_view(), name="leaves"),
    path("attendance/leave/<str:leave_id>/", v.LeaveView.as_view(), name="leave"),
    path(
        "attendance/leave/<str:leave_id>/decide/", v.LeaveDecideView.as_view(), name="leave-decide"
    ),
    path(
        "attendance/leave/<str:leave_id>/cancel/", v.LeaveCancelView.as_view(), name="leave-cancel"
    ),
    path("attendance/staff/register/", v.StaffRegisterView.as_view(), name="staff-register"),
    path(
        "attendance/staff/register/save/",
        v.StaffRegisterSaveView.as_view(),
        name="staff-register-save",
    ),
    path("attendance/staff/mine/", v.MyStaffDaysView.as_view(), name="staff-mine"),
]
