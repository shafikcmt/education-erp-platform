"""Portal routes (Phase 7 M8). Tenant host only."""

from django.urls import path

from apps.parent_portal.api import views as v

app_name = "parent_portal"

urlpatterns = [
    path("portal/children/", v.ChildrenView.as_view(), name="children"),
    path("portal/children/<str:student_id>/", v.ChildDetailView.as_view(), name="child"),
]
