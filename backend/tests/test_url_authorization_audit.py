"""Owner requirement 6 / plan §8: every API view enforces a server-side permission.

Enumerates all URL patterns. Each DRF view must carry a ``PermissionCheck`` subclass that maps
**every** HTTP method the view implements to a registered permission code, unless the route is on
the reviewed allow-list below (anonymous auth endpoints and session-only endpoints).
"""

from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.identity.permissions import IsAuthenticatedSession
from apps.rbac.permissions import PermissionCheck
from apps.rbac.registry import declared_permissions

# Reviewed allow-list. Each entry: route name -> why it has no permission code.
ANONYMOUS = {
    "core:system-health": "public liveness summary (status + version only)",
    "identity:auth-csrf": "sets the CSRF cookie",
    "identity:auth-login": "credential check; throttled; enumeration-safe",
    "identity:auth-mfa-verify": "second factor of a pending login; throttled",
    "identity:auth-password-reset": "always 202; throttled",
    "identity:auth-password-reset-confirm": "single-use token",
    "identity:auth-activate": "single-use token",
    "identity:auth-activation-resend": "always 202; throttled",
    "identity:auth-email-verify": "single-use token",
    # Phase 3 M8 (tenant host only)
    "tenancy:public-tenant": "name, languages and branding for the sign-in page",
    "tenancy:invitation-accept": "single-use invitation token; enumeration-safe; durable audit",
}
SESSION_ONLY = {
    "identity:auth-logout": "ends the caller's own session",
    "identity:auth-step-up": "re-authenticates the caller's own session",
}
METHODS = ("get", "post", "put", "patch", "delete")


def _walk(patterns, namespace=""):
    for entry in patterns:
        if isinstance(entry, URLResolver):
            ns = f"{namespace}{entry.namespace}:" if entry.namespace else namespace
            yield from _walk(entry.url_patterns, ns)
        elif isinstance(entry, URLPattern):
            yield f"{namespace}{entry.name}", entry


def _api_views():
    for name, pattern in _walk(get_resolver().url_patterns):
        view_class = getattr(pattern.callback, "view_class", None)
        if view_class is not None and issubclass(view_class, APIView):
            yield name, view_class


def test_every_api_view_is_authorized_or_reviewed():
    known = set(declared_permissions())
    problems = []
    views = list(_api_views())
    assert len(views) >= 35  # guards against the walk silently finding nothing
    for name, view in views:
        classes = list(view.permission_classes)
        implemented = [m.upper() for m in METHODS if hasattr(view, m)]
        if name in ANONYMOUS:
            if classes != [AllowAny]:
                problems.append(f"{name}: anonymous allow-list entry must use AllowAny only")
            continue
        if name in SESSION_ONLY:
            if IsAuthenticatedSession not in classes:
                problems.append(f"{name}: session-only entry must use IsAuthenticatedSession")
            continue
        checks = [c for c in classes if isinstance(c, type) and issubclass(c, PermissionCheck)]
        if not checks:
            problems.append(f"{name}: no HasPermission")
            continue
        for method in implemented:
            codes = [c.code_for(method) for c in checks]
            if not all(codes):
                problems.append(f"{name}: {method} has no permission code")
            unknown = [c for c in codes if c and c not in known]
            if unknown:
                problems.append(f"{name}: unknown permission codes {unknown}")
    assert not problems, "\n".join(problems)


def test_allow_list_entries_still_exist():
    names = {name for name, _ in _api_views()}
    assert set(ANONYMOUS) | set(SESSION_ONLY) <= names


def test_every_tenant_host_view_declares_its_module():
    """Phase 4 M4 (plan §4): every view reachable on a tenant host declares ``module_code``,
    an installed module. Views of non-platform modules must enforce ``ModuleEntitled`` for
    that code before the permission check. Platform-only views are exempt."""
    from apps.core.hosts import TENANT, host_classes_of
    from apps.module_registry.permissions import ModuleCheck, ModuleGatedView
    from apps.module_registry.registry import installed_manifests

    installed = installed_manifests()
    problems, tenant_views = [], 0
    for name, pattern in _walk(get_resolver().url_patterns):
        view = getattr(pattern.callback, "view_class", None)
        if view is None or not issubclass(view, APIView):
            continue
        if TENANT not in host_classes_of(pattern.callback):
            continue
        tenant_views += 1
        code = getattr(view, "module_code", "")
        if not code:
            problems.append(f"{name}: no module_code")
            continue
        if code not in installed:
            problems.append(f"{name}: unknown or uninstalled module {code!r}")
            continue
        if installed[code].category == "platform":
            continue
        gated = issubclass(view, ModuleGatedView) or any(
            isinstance(c, type) and issubclass(c, ModuleCheck) and c.module_code == code
            for c in view.permission_classes
        )
        if not gated:
            problems.append(f"{name}: module {code!r} is not enforced with ModuleEntitled")
    assert tenant_views >= 30  # guards against the walk silently finding nothing
    assert not problems, "\n".join(problems)
