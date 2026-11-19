"""Completeness gate of the platform operation catalogue (Phase 3 plan §6.3, §12.2; M8).

* Every platform-host view of the tenancy API declares, for each HTTP method it implements, the
  catalogue operation it performs (``platform_operations``); each id must exist and be enabled.
* Every user-facing platform operation of plan §12.2 (P2, P4, P5, P6, P8) is reachable through
  at least one declared view, so the catalogue and the API can't drift apart.
* Disabled operations (P3, P11, P15, P16) are never declared by a view.
"""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.views import APIView

from apps.core import hosts
from apps.core.tenancy.platform import CATALOGUE

METHODS = ("get", "post", "put", "patch", "delete")
EXPECTED = {"P2", "P4", "P5", "P6", "P8"}


def _views(patterns=None):
    for entry in patterns if patterns is not None else get_resolver().url_patterns:
        if isinstance(entry, URLResolver):
            yield from _views(entry.url_patterns)
        elif isinstance(entry, URLPattern):
            view = getattr(entry.callback, "view_class", None)
            if view is not None and issubclass(view, APIView):
                yield str(entry.pattern), view


def test_tenancy_platform_views_declare_enabled_catalogue_operations():
    declared: set[str] = set()
    problems = []
    for route, view in _views():
        if not view.__module__.startswith("apps.tenancy.api"):
            continue
        if hosts.PLATFORM not in hosts.host_classes_of(view):
            assert not hasattr(view, "platform_operations"), route
            continue
        operations = getattr(view, "platform_operations", None)
        if not operations:
            problems.append(f"{route}: no platform_operations")
            continue
        for method in (m.upper() for m in METHODS if hasattr(view, m)):
            op = operations.get(method)
            if op is None:
                problems.append(f"{route} {method}: no catalogue operation")
            elif op not in CATALOGUE or not CATALOGUE[op].enabled:
                problems.append(f"{route} {method}: {op} is not an enabled operation")
            else:
                declared.add(op)
    assert not problems, "\n".join(problems)
    assert declared == EXPECTED


def test_platform_and_tenant_routes_never_overlap():
    tenant: set[str] = set()
    platform: set[str] = set()
    for route, view in _views():
        classes = hosts.host_classes_of(view)
        (tenant if classes == hosts.TENANT_ONLY else platform).add(route)
    assert not tenant & platform
    assert not any(r.startswith("platform/") for r in tenant)
