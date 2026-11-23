"""Root URL configuration.

* ``/healthz`` and ``/readyz`` — infrastructure probes (not part of the public API schema).
* ``/api/v1/`` — versioned REST API (ADR-015).
* ``/api/schema/`` and ``/api/docs/`` — OpenAPI, only when ``API_DOCS_ENABLED``.
"""

from django.conf import settings
from django.urls import URLPattern, URLResolver, include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.exceptions import api_not_found
from apps.core.health import healthz, readyz

urlpatterns: list[URLPattern | URLResolver] = [
    path("healthz", healthz, name="healthz"),
    path("readyz", readyz, name="readyz"),
    path("api/v1/", include("apps.core.urls")),
    path("api/v1/", include("apps.identity.urls")),
    path("api/v1/", include("apps.rbac.urls")),
    path("api/v1/", include("apps.audit.urls")),
    path("api/v1/", include("apps.tenancy.urls")),
    path("api/v1/", include("apps.module_registry.urls")),
    path("api/v1/", include("apps.billing.urls")),
    path("api/v1/", include("apps.customization.urls")),
    path("api/v1/", include("apps.notifications_core.urls")),
    path("api/v1/", include("apps.academics.urls")),
    path("api/v1/", include("apps.files.urls")),
    path("api/v1/", include("apps.admissions.urls")),
]

if settings.API_DOCS_ENABLED:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-docs"),
    ]

# Unknown API routes always return Problem Details (also with DEBUG=True, where Django would
# otherwise render its HTML debug page). Must stay last.
urlpatterns.append(re_path(r"^api/", api_not_found, name="api-not-found"))

handler404 = "apps.core.exceptions.handler404"
handler500 = "apps.core.exceptions.handler500"
