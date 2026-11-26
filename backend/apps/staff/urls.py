"""Staff routes (Phase 7 M3). Tenant host only."""

from django.urls import path

from apps.staff.api import views as v

app_name = "staff"

urlpatterns = [
    path("staff/", v.StaffView.as_view(), name="staff"),
    path("staff/departments/", v.DepartmentsView.as_view(), name="departments"),
    path(
        "staff/departments/<str:department_id>/",
        v.DepartmentDetailView.as_view(),
        name="department",
    ),
    path("staff/designations/", v.DesignationsView.as_view(), name="designations"),
    path(
        "staff/designations/<str:designation_id>/",
        v.DesignationDetailView.as_view(),
        name="designation",
    ),
    path("staff/advisors/", v.AdvisorsView.as_view(), name="advisors"),
    path("staff/advisors/<str:advisor_id>/", v.AdvisorDetailView.as_view(), name="advisor"),
    # Last: the specific routes above win over a profile id.
    path("staff/<str:profile_id>/", v.StaffDetailView.as_view(), name="profile"),
]
