"""rbac routes, mounted under /api/v1/ (plan §8)."""

from django.urls import path

from apps.rbac import api

app_name = "rbac"

urlpatterns = [
    path("platform/permissions/", api.PermissionsView.as_view(), name="platform-permissions"),
    path("platform/roles/", api.RolesView.as_view(), name="platform-roles"),
    path("platform/roles/<str:role_id>/", api.RoleDetailView.as_view(), name="platform-role"),
    path(
        "platform/users/<str:user_id>/platform-roles/",
        api.UserPlatformRolesView.as_view(),
        name="platform-user-roles",
    ),
    path(
        "platform/users/<str:user_id>/platform-roles/<str:assignment_id>/",
        api.UserPlatformRoleDetailView.as_view(),
        name="platform-user-role",
    ),
]
