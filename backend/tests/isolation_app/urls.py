"""Test-only URL conf: the real routes plus probe endpoints for the tenant request path
(Phase 3 M3). Never installed outside the test settings."""

from django.urls import path

from config.urls import handler404, handler500
from config.urls import urlpatterns as real_urlpatterns
from tests.isolation_app import views

urlpatterns = [
    path("_probe/whoami/", views.WhoAmI.as_view()),
    path("_probe/records/", views.Records.as_view()),
    path("_probe/protected/", views.Protected.as_view()),
    path("_probe/tenant-protected/", views.TenantProtected.as_view()),
    path("_probe/platform-only/", views.PlatformOnly.as_view()),
    path("_probe/tenant-only/", views.TenantOnly.as_view()),
    *real_urlpatterns,
]

__all__ = ["handler404", "handler500", "urlpatterns"]
