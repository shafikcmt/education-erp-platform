"""Permission classes of the tenant-host API (Phase 3 M8; plan §12.1).

A tenant request is authorised at tenant scope (``request.scope_target``). Many tenant objects
live in narrower scopes (an institution admin manages one institution), so these classes let a
request through when the actor holds the code **in any scope of this tenant**; the view then
filters lists to the scopes the actor covers, and every service checks the exact object scope
again, uncached. Holding a code somewhere is necessary, never sufficient.
"""

from __future__ import annotations

from typing import Any

from rest_framework.request import Request

from apps.rbac.engine import ScopeTarget, has_perm
from apps.rbac.models import RoleAssignment
from apps.rbac.permissions import AnyPermissionCheck, HasAnyPermission, HasPermission
from apps.tenancy.models import Membership
from apps.tenancy.rbac_sources import live_assignments


def actor_targets(user: Any, tenant_id: Any) -> list[ScopeTarget]:
    """The tenant target followed by every scope in which ``user`` holds a live assignment."""
    targets = [ScopeTarget(tenant_id=tenant_id)]
    rows = (
        RoleAssignment.objects.filter(
            live_assignments(),
            membership__user_id=user.pk,
            membership__status=Membership.Status.ACTIVE,
        )
        .values_list("institution_id", "campus_id")
        .distinct()
    )
    for institution_id, campus_id in rows:
        target = ScopeTarget(tenant_id, institution_id, campus_id)
        if target not in targets:
            targets.append(target)
    return targets


def holds_in_some_scope(user: Any, code: str, tenant_id: Any) -> bool:
    return any(has_perm(user, code, target=t) for t in actor_targets(user, tenant_id))


class _AnyTenantScope:
    def holds(self, request: Request, user: Any, code: str) -> bool:
        tenant = getattr(request, "tenant", None)
        return tenant is not None and holds_in_some_scope(user, code, tenant.id)


def HasTenantPermission(codes: str | dict[str, str]) -> type[Any]:  # noqa: N802
    """Like ``HasPermission``, granted when the code is held in any scope of this tenant."""
    base = HasPermission(codes)
    return type(f"Tenant{base.__name__}", (_AnyTenantScope, base), {})


def HasTenantAnyPermission(*codes: str) -> type[AnyPermissionCheck]:  # noqa: N802
    base = HasAnyPermission(*codes)
    return type(f"Tenant{base.__name__}", (_AnyTenantScope, base), {})


def visible_institution(user: Any, code: str, institution_id: Any) -> Any:
    """The institution when ``user`` holds ``code`` there or at one of its campuses, else
    ``NotFound`` (an unknown and a foreign institution are indistinguishable). For list views of
    institution-bound modules (Phase 6); services still check the exact scope."""
    from django.core.exceptions import ValidationError
    from rest_framework.exceptions import NotFound

    from apps.tenancy.models import Campus, Institution

    try:
        inst = Institution.objects.filter(pk=institution_id).first()
    except (ValueError, ValidationError):
        inst = None
    if inst is None:
        raise NotFound()
    targets = [ScopeTarget(inst.tenant_id, inst.pk)] + [
        ScopeTarget(inst.tenant_id, inst.pk, campus)
        for campus in Campus.objects.filter(institution=inst).values_list("pk", flat=True)
    ]
    if not any(has_perm(user, code, target=t, use_cache=False) for t in targets):
        raise NotFound()
    return inst
