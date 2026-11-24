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
    # Phase 4 M5: the organisation's own plan, modules and limits (read-only)
    "api/v1/tenant/subscription/": False,
    # Phase 5 M6: Customization Studio and the notification inbox (signed-in members only)
    # Phase 6 M4: admissions back office (module-gated, behind the membership gate)
    "api/v1/admissions/inquiries/": False,
    "api/v1/admissions/inquiries/<str:inquiry_id>/": False,
    "api/v1/admissions/cycles/": False,
    "api/v1/admissions/cycles/<str:cycle_id>/targets/": False,
    "api/v1/admissions/cycles/<str:cycle_id>/status/": False,
    "api/v1/admissions/applications/": False,
    "api/v1/admissions/applications/<str:application_id>/": False,
    "api/v1/admissions/applications/<str:application_id>/review/": False,
    "api/v1/admissions/applications/<str:application_id>/decision/": False,
    "api/v1/admissions/applications/<str:application_id>/offer-response/": False,
    # Phase 6 M6: admission tests, scores and the merit list (members only)
    "api/v1/admissions/cycles/<str:cycle_id>/tests/": False,
    "api/v1/admissions/tests/": False,
    "api/v1/admissions/tests/<str:test_id>/assignments/": False,
    "api/v1/admissions/assignments/<str:assignment_id>/": False,
    "api/v1/admissions/applications/<str:application_id>/evaluate/": False,
    "api/v1/admissions/targets/<str:target_id>/merit/": False,
    "api/v1/admissions/targets/<str:target_id>/merit/publish/": False,
    "api/v1/admissions/targets/<str:target_id>/merit/offers/": False,
    # Phase 6 M5: application documents (staff) and the public admissions flow (anonymous:
    # skips the membership gate; throttled, enumeration-safe, 404 without the module)
    "api/v1/admissions/applications/<str:application_id>/documents/": False,
    "api/v1/admissions/applications/<str:application_id>/documents/<str:file_id>/download/": False,
    "api/v1/public/admissions/cycles/": True,
    "api/v1/public/admissions/cycles/<str:cycle_id>/form/": True,
    "api/v1/public/admissions/cycles/<str:cycle_id>/visibility/": True,
    "api/v1/public/admissions/cycles/<str:cycle_id>/apply/": True,
    "api/v1/public/admissions/verify/": True,
    "api/v1/public/admissions/status/": True,
    "api/v1/public/admissions/status/respond/": True,
    "api/v1/public/admissions/status/documents/": True,
    "api/v1/public/admissions/status/documents/confirm/": True,
    # Phase 6 M3: files (module-gated, behind the membership gate)
    "api/v1/files/uploads/": False,
    "api/v1/files/<str:file_id>/": False,
    "api/v1/files/<str:file_id>/confirm/": False,
    "api/v1/files/<str:file_id>/download/": False,
    # Phase 6 M2: academics (module-gated, behind the membership gate)
    "api/v1/academics/setup/": False,
    "api/v1/academics/years/": False,
    "api/v1/academics/years/<str:year_id>/status/": False,
    "api/v1/academics/years/<str:year_id>/terms/": False,
    "api/v1/academics/units/": False,
    "api/v1/academics/units/<str:unit_id>/": False,
    "api/v1/academics/units/<str:unit_id>/archive/": False,
    "api/v1/academics/subjects/": False,
    "api/v1/academics/subjects/<str:subject_id>/archive/": False,
    "api/v1/academics/offerings/": False,
    "api/v1/academics/offerings/<str:offering_id>/teachers/": False,
    "api/v1/academics/offerings/<str:offering_id>/teachers/<str:teacher_id>/": False,
    "api/v1/customization/catalog/": False,
    "api/v1/customization/config/": False,
    "api/v1/customization/config/publish/": False,
    "api/v1/customization/config/rollback/": False,
    "api/v1/customization/fields/": False,
    "api/v1/customization/fields/<str:field_id>/": False,
    "api/v1/customization/fields/<str:field_id>/deprecate/": False,
    "api/v1/customization/rules/": False,
    "api/v1/customization/rules/test/": False,
    "api/v1/customization/rules/<str:key>/publish/": False,
    "api/v1/customization/forms/": False,
    "api/v1/customization/forms/<str:key>/publish/": False,
    "api/v1/customization/forms/<str:key>/render/": False,
    "api/v1/customization/forms/<str:key>/visibility/": False,
    "api/v1/customization/forms/<str:key>/validate/": False,
    "api/v1/customization/workflows/": False,
    "api/v1/customization/workflows/<str:key>/publish/": False,
    "api/v1/customization/workflows/<str:key>/start/": False,
    "api/v1/customization/workflow-requests/<str:instance_id>/": False,
    "api/v1/customization/workflow-requests/<str:instance_id>/transition/": False,
    "api/v1/customization/templates/": False,
    "api/v1/customization/templates/preview/": False,
    "api/v1/customization/templates/<str:key>/publish/": False,
    "api/v1/customization/numbering/": False,
    "api/v1/notifications/": False,
    "api/v1/notifications/read/": False,
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
