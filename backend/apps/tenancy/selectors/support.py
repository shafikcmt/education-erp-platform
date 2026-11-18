"""Read side of support sessions for tenant members (Phase 3 M5; plan §11.1, S5).

* :func:`banner` — what every member sees while support access is possible right now (the
  API exposes it through ``/me/context/`` in M8).
* :func:`history` — the tenant's full support history for members holding
  ``tenancy.support_session.view``.
Both run inside the tenant transaction, so only this tenant's sessions exist (RLS).
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.core.tenancy import require_tenant
from apps.rbac.engine import ScopeTarget, require_perm
from apps.tenancy.models import SupportSession
from apps.tenancy.support import USABLE_STATUSES

_FIELDS = ("id", "status", "ticket_ref", "requested_at", "starts_at", "ends_at")


def banner() -> list[dict[str, Any]]:
    now = timezone.now()
    rows: list[dict[str, Any]] = [
        dict(row)
        for row in SupportSession.objects.filter(
            status__in=USABLE_STATUSES, starts_at__lte=now, ends_at__gt=now
        )
        .order_by("ends_at")
        .values("id", "status", "ticket_ref", "starts_at", "ends_at")
    ]
    return rows


def history(*, actor: Any) -> list[dict[str, Any]]:
    ctx = require_tenant()
    require_perm(actor, "tenancy.support_session.view", target=ScopeTarget(ctx.id))
    return list(
        SupportSession.objects.order_by("-requested_at").values(
            *_FIELDS, "reason", "staff_user_id", "approved_by", "revoked_by", "ended_at"
        )
    )
