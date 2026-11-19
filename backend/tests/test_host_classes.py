"""Which routes a tenant host may serve (Phase 3 M3; plan §12; owner decision Q2).

Views are platform-only unless they opt in with ``host_classes``. This reviewed allow-list
must be edited, in the same change, whenever a route becomes reachable on tenant hosts.
"""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, get_resolver

from apps.core import hosts

# route -> skips the membership gate (sign-in and sign-out flows, the public sign-in page data
# and invitation acceptance only)
TENANT_HOST_ROUTES = {
    "api/v1/auth/csrf/": True,
    "api/v1/auth/login/": True,
    "api/v1/auth/mfa/verify/": True,
    "api/v1/auth/logout/": True,
    "api/v1/me/": False,
    # Phase 3 M8: own step-up and MFA enrolment (behind the membership gate)
    "api/v1/auth/step-up/": False,
    "api/v1/me/mfa/": False,
    "api/v1/me/mfa/totp/setup/": False,
    "api/v1/me/mfa/totp/setup/<str:device_id>/": False,
    "api/v1/me/mfa/totp/setup/<str:device_id>/manual-key/": False,
    "api/v1/me/mfa/totp/confirm/": False,
    "api/v1/me/mfa/recovery-codes/": False,
    # Phase 3 M8 (plan §12.1): tenant-only routes
    "api/v1/public/tenant/": True,
    "api/v1/auth/invitations/accept/": True,
    "api/v1/me/context/": False,
    "api/v1/tenant/": False,
    "api/v1/tenant/support-approval/": False,
    "api/v1/institutions/": False,
    "api/v1/institutions/<str:institution_id>/": False,
    "api/v1/institutions/<str:institution_id>/archive/": False,
    "api/v1/institutions/<str:institution_id>/campuses/": False,
    "api/v1/campuses/<str:campus_id>/": False,
    "api/v1/campuses/<str:campus_id>/archive/": False,
    "api/v1/members/": False,
    "api/v1/members/<str:member_id>/": False,
    "api/v1/members/<str:member_id>/role-assignments/": False,
    "api/v1/members/<str:member_id>/role-assignments/<str:assignment_id>/": False,
    "api/v1/roles/": False,
    "api/v1/roles/<str:role_id>/": False,
    "api/v1/roles/<str:role_id>/clone/": False,
    "api/v1/invitations/": False,
    "api/v1/invitations/<str:invitation_id>/": False,
    "api/v1/invitations/<str:invitation_id>/resend/": False,
    "api/v1/support-sessions/": False,
    "api/v1/support-sessions/<str:session_id>/approve/": False,
    "api/v1/support-sessions/<str:session_id>/reject/": False,
    "api/v1/support-sessions/<str:session_id>/revoke/": False,
    "api/v1/audit-events/": False,
    "api/v1/audit-events/<str:event_id>/reveal-ip/": False,
}
# Routes served on both kinds of host (everything else on this list is tenant-only).
BOTH_HOSTS = {
    "api/v1/auth/csrf/",
    "api/v1/auth/login/",
    "api/v1/auth/mfa/verify/",
    "api/v1/auth/logout/",
    "api/v1/me/",
    "api/v1/auth/step-up/",
    "api/v1/me/mfa/",
    "api/v1/me/mfa/totp/setup/",
    "api/v1/me/mfa/totp/setup/<str:device_id>/",
    "api/v1/me/mfa/totp/setup/<str:device_id>/manual-key/",
    "api/v1/me/mfa/totp/confirm/",
    "api/v1/me/mfa/recovery-codes/",
}
# Restricted owner mode on suspended tenants (D2): only these views are served.
SUSPENDED_TENANT_ROUTES = {
    "api/v1/me/context/",
    "api/v1/support-sessions/",
    "api/v1/support-sessions/<str:session_id>/approve/",
    "api/v1/support-sessions/<str:session_id>/reject/",
    "api/v1/support-sessions/<str:session_id>/revoke/",
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


def test_tenant_only_routes_and_gate_exemptions_are_the_reviewed_ones():
    for route, view in _routes():
        classes = hosts.host_classes_of(view)
        view_class = hosts.view_class(view)
        if hosts.TENANT in classes:
            assert (hosts.PLATFORM in classes) == (route in BOTH_HOSTS), route
        if getattr(view_class, "tenant_auth_flow", False):
            assert TENANT_HOST_ROUTES.get(route) is True, route
        if getattr(view_class, "suspended_tenant_allowed", False):
            assert route in SUSPENDED_TENANT_ROUTES, route
    allowed = {
        route
        for route, view in _routes()
        if getattr(hosts.view_class(view), "suspended_tenant_allowed", False)
    }
    assert allowed == SUSPENDED_TENANT_ROUTES


def test_undeclared_views_default_to_platform_only():
    def plain_view(request):  # pragma: no cover - never called
        return None

    assert hosts.host_classes_of(plain_view) == hosts.PLATFORM_ONLY
    assert {"platform", "tenant"} == hosts.PLATFORM_AND_TENANT
