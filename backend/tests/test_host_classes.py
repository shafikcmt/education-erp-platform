"""Which routes a tenant host may serve (Phase 3 M3; plan §12; owner decision Q2).

Views are platform-only unless they opt in with ``host_classes``. This reviewed allow-list
must be edited, in the same change, whenever a route becomes reachable on tenant hosts.
"""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, get_resolver

from apps.core import hosts

# route -> skips the membership gate (sign-in and sign-out flows only)
TENANT_HOST_ROUTES = {
    "api/v1/auth/csrf/": True,
    "api/v1/auth/login/": True,
    "api/v1/auth/mfa/verify/": True,
    "api/v1/auth/logout/": True,
    "api/v1/me/": False,
}


def _routes(patterns=None, prefix=""):
    for entry in patterns if patterns is not None else get_resolver().url_patterns:
        route = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from _routes(entry.url_patterns, route)
        elif isinstance(entry, URLPattern):
            yield route, entry.callback


def test_only_the_reviewed_routes_are_reachable_on_tenant_hosts():
    exposed = {
        route: bool(getattr(hosts.view_class(view), "tenant_auth_flow", False))
        for route, view in _routes()
        if hosts.TENANT in hosts.host_classes_of(view)
    }
    assert exposed == TENANT_HOST_ROUTES


def test_no_production_route_is_tenant_only_yet_and_gate_exemptions_are_minimal():
    for route, view in _routes():
        classes = hosts.host_classes_of(view)
        assert hosts.PLATFORM in classes, route  # tenant-only APIs arrive with M8
        if getattr(hosts.view_class(view), "tenant_auth_flow", False):
            assert TENANT_HOST_ROUTES.get(route) is True, route


def test_undeclared_views_default_to_platform_only():
    def plain_view(request):  # pragma: no cover - never called
        return None

    assert hosts.host_classes_of(plain_view) == hosts.PLATFORM_ONLY
    assert {"platform", "tenant"} == hosts.PLATFORM_AND_TENANT
