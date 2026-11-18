"""Support sessions (Phase 3 M5; plan §11; ADR-045; decisions D2, D5).

* **Request / end (platform staff, platform operation P6):** inside ``platform_scope("P6")``
  with the uncached ``tenancy.support_session.request`` check, one targeted tenant transaction
  writes the session (mechanism T). A reason (at least 10 characters), a ticket reference and a
  length of 15-120 minutes are required. Requests are allowed while the tenant is suspended
  (D2), but such a session can't be used until the tenant is active again.
* **Approve / reject / revoke (tenant members):** ``tenancy.support_session.approve`` or
  ``.revoke`` in the tenant scope, checked without the cache. Nobody approves their own session
  (S6). The window starts at approval and is never extended.
* **Approval setting (D5):** only an active tenant owner holding ``tenancy.tenant.update`` may
  change ``support_access_requires_approval``, with a reason; the change is audited in the same
  transaction and the owners are emailed. With approval off, a request is approved at once but
  stays time-limited, visible and revocable.
* Every step is audited in the tenant's log; owners are emailed after commit on request,
  approval, start and setting changes. Revoking, ending, expiring and suspending end the staff
  member's sessions on this tenant's hosts (S7).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.models import ActorType
from apps.audit.services import record
from apps.core.tenancy import TenantContext, tenant_atomic
from apps.core.tenancy.platform import platform_scope
from apps.identity.models import SessionRecord, User
from apps.identity.services import sessions as identity_sessions
from apps.identity.services.notifications import send_security_email
from apps.rbac.engine import ScopeTarget, bump_tenant_version, require_perm
from apps.rbac.models import RoleAssignment
from apps.rbac.role_templates import TENANT_OWNER
from apps.rbac.services import GuardRailViolation
from apps.tenancy.models import Membership, SupportSession, Tenant, TenantDomain
from apps.tenancy.rbac_sources import live_assignments
from apps.tenancy.rules import RESOLVABLE_STATUSES
from apps.tenancy.services import common

if TYPE_CHECKING:
    from django.http import HttpRequest

Status = SupportSession.Status
REQUEST = "tenancy.support_session.request"
APPROVE = "tenancy.support_session.approve"
REVOKE = "tenancy.support_session.revoke"
MIN_MINUTES, MAX_MINUTES = 15, 120
_REASON_MIN = 10
APPROVAL_SETTING = "support_access_requires_approval"


# --------------------------------------------------------------------------- helpers
def owner_emails() -> list[str]:
    """Email addresses of the current tenant's active owners."""
    user_ids = RoleAssignment.objects.filter(
        live_assignments(),
        scope_type="tenant",
        role__is_system=True,
        role__template__code=TENANT_OWNER,
        membership__status=Membership.Status.ACTIVE,
    ).values_list("membership__user_id", flat=True)
    return sorted(
        User.objects.filter(pk__in=list(user_ids), is_active=True).values_list("email", flat=True)
    )


def _notify_owners(template: str, context: dict[str, Any]) -> None:
    recipients = owner_emails()  # resolved now, inside the tenant transaction

    def deliver() -> None:
        for email in recipients:
            send_security_email(template, to=email, user=None, context=context)

    transaction.on_commit(deliver)


def _audit(
    action: str,
    session: SupportSession,
    *,
    actor: Any = None,
    actor_type: str | None = None,
    request: HttpRequest | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    record(
        action,
        actor=actor,
        actor_type=actor_type,
        request=request,
        support_session_id=session.pk,
        target_type="tenancy.supportsession",
        target_id=session.pk,
        metadata=metadata,
    )


def end_staff_host_sessions(session: SupportSession, *, reason: str) -> int:
    """End the staff member's sign-ins on THIS tenant's hosts only (S7, S9)."""
    hosts = list(TenantDomain.objects.values_list("domain", flat=True))
    if not hosts:
        return 0
    return identity_sessions.revoke_records(
        SessionRecord.objects.filter(user_id=session.staff_user_id, host__in=hosts),
        reason=reason,
    )


def _open_window(session: SupportSession, *, approved_by: Any) -> None:
    now = timezone.now()
    session.status = Status.APPROVED
    session.approved_by = approved_by
    session.starts_at = now
    session.ends_at = now + timedelta(minutes=session.duration_minutes)


def _approval_required(tenant: Tenant) -> bool:
    settings_value = tenant.settings if isinstance(tenant.settings, dict) else {}
    return settings_value.get(APPROVAL_SETTING, True) is not False


# --------------------------------------------------------------------------- platform side (P6)
def request_session(
    *,
    actor: User,
    tenant_id: uuid.UUID,
    reason: str,
    ticket_ref: str,
    minutes: int,
    request: HttpRequest | None = None,
) -> SupportSession:
    """Platform staff ask for read-only access to one tenant (P6, mechanism T)."""
    cleaned_reason = (reason or "").strip()
    ticket = (ticket_ref or "").strip()
    if len(cleaned_reason) < _REASON_MIN:
        raise ValidationError({"reason": "Explain the reason in at least 10 characters."})
    if not ticket or len(ticket) > 64:
        raise ValidationError({"ticket_ref": "A ticket reference is required."})
    if not isinstance(minutes, int) or not MIN_MINUTES <= minutes <= MAX_MINUTES:
        raise ValidationError({"minutes": "Choose between 15 and 120 minutes."})
    with platform_scope(operation="P6", actor=actor, reason=f"support: {ticket}"):
        tenant = Tenant.objects.filter(pk=tenant_id, status__in=RESOLVABLE_STATUSES).first()
        if tenant is None:
            raise ValidationError({"tenant": "Unknown tenant."})
        with tenant_atomic(tenant.as_context()):
            locked = Tenant.objects.select_for_update().get(pk=tenant.pk)
            if SupportSession.objects.filter(
                staff_user=actor, status__in=SupportSession.OPEN_STATUSES
            ).exists():
                raise ValidationError({"tenant": "You already have an open support session."})
            session = SupportSession(
                staff_user=actor,
                reason=cleaned_reason,
                ticket_ref=ticket,
                requested_at=timezone.now(),
                duration_minutes=minutes,
            )
            auto = not _approval_required(locked)
            if auto:
                _open_window(session, approved_by=None)
            session.save()
            _audit(
                "support.session.requested",
                session,
                actor=actor,
                actor_type=ActorType.SUPPORT,
                request=request,
                metadata={"minutes": minutes, "auto_approved": auto},
            )
            _notify_owners(
                "support_session_requested",
                {
                    "tenant_name": locked.name,
                    "staff_email": actor.email,
                    "reason": cleaned_reason,
                    "ticket_ref": ticket,
                    "minutes": minutes,
                    "auto_approved": auto,
                },
            )
    return session


def end_session(
    *, actor: User, tenant_id: uuid.UUID, session_id: uuid.UUID, request: HttpRequest | None = None
) -> SupportSession:
    """Platform staff end their own session early (P6)."""
    with platform_scope(operation="P6", actor=actor, reason="end own support session"):
        tenant = Tenant.objects.filter(pk=tenant_id).first()
        if tenant is None:
            raise ValidationError({"session": "Unknown session."})
        with tenant_atomic(tenant.as_context()):
            session = (
                SupportSession.objects.select_for_update()
                .filter(pk=session_id, staff_user=actor)
                .first()
            )
            if session is None:
                raise ValidationError({"session": "Unknown session."})
            if session.status in SupportSession.OPEN_STATUSES:
                session.status = Status.ENDED
                session.ended_at = timezone.now()
                session.save(update_fields=["status", "ended_at", "updated_at"])
                end_staff_host_sessions(session, reason="support_session_ended")
                _audit(
                    "support.session.ended",
                    session,
                    actor=actor,
                    actor_type=ActorType.SUPPORT,
                    request=request,
                )
    return session


# --------------------------------------------------------------------------- tenant side
def _tenant_session(session: SupportSession | uuid.UUID) -> SupportSession:
    pk = session.pk if isinstance(session, SupportSession) else session
    found = SupportSession.objects.select_for_update().filter(pk=pk).first()
    if found is None:
        raise ValidationError({"session": "Unknown session."})
    return found


@transaction.atomic
def approve_session(
    *, actor: User, session: SupportSession | uuid.UUID, request: HttpRequest | None = None
) -> SupportSession:
    ctx = common.tenant_context()
    require_perm(actor, APPROVE, target=ScopeTarget(ctx.id), use_cache=False)
    found = _tenant_session(session)
    if found.staff_user_id == actor.pk:
        raise GuardRailViolation("cannot_act_on_self", "You cannot approve your own access.")
    if found.status != Status.REQUESTED:
        raise ValidationError({"session": "Only a requested session can be approved."})
    _open_window(found, approved_by=actor.pk)
    found.save(update_fields=["status", "approved_by", "starts_at", "ends_at", "updated_at"])
    _audit(
        "support.session.approved",
        found,
        actor=actor,
        request=request,
        metadata={"minutes": found.duration_minutes},
    )
    return found


@transaction.atomic
def reject_session(
    *, actor: User, session: SupportSession | uuid.UUID, request: HttpRequest | None = None
) -> SupportSession:
    ctx = common.tenant_context()
    require_perm(actor, APPROVE, target=ScopeTarget(ctx.id), use_cache=False)
    found = _tenant_session(session)
    if found.status != Status.REQUESTED:
        raise ValidationError({"session": "Only a requested session can be rejected."})
    found.status = Status.REJECTED
    found.ended_at = timezone.now()
    found.save(update_fields=["status", "ended_at", "updated_at"])
    _audit("support.session.rejected", found, actor=actor, request=request)
    return found


@transaction.atomic
def revoke_session(
    *, actor: User, session: SupportSession | uuid.UUID, request: HttpRequest | None = None
) -> SupportSession:
    ctx = common.tenant_context()
    require_perm(actor, REVOKE, target=ScopeTarget(ctx.id), use_cache=False)
    found = _tenant_session(session)
    if found.status in SupportSession.OPEN_STATUSES:
        _close(found, Status.REVOKED, revoked_by=actor.pk)
        _audit(
            "support.session.revoked",
            found,
            actor=actor,
            request=request,
            metadata={"reason": "tenant"},
        )
    return found


def _close(session: SupportSession, status: str, *, revoked_by: Any = None) -> None:
    session.status = status
    session.ended_at = timezone.now()
    session.revoked_by = revoked_by
    session.save(update_fields=["status", "ended_at", "revoked_by", "updated_at"])
    end_staff_host_sessions(session, reason=f"support_session_{status}")


def revoke_open_sessions(*, reason: str) -> int:
    """Revoke every open session of the current tenant (tenant suspension, D2). Called by the
    suspension service (P5, M8) inside the tenant transaction."""
    common.tenant_context()
    count = 0
    for found in SupportSession.objects.select_for_update().filter(
        status__in=SupportSession.OPEN_STATUSES
    ):
        _close(found, Status.REVOKED)
        _audit(
            "support.session.revoked",
            found,
            actor_type=ActorType.SYSTEM,
            metadata={"reason": reason[:40]},
        )
        count += 1
    return count


def mark_started(session: SupportSession, *, request: HttpRequest | None = None) -> None:
    """First use of an approved session (request gate): ``active``, audited, owners told."""
    updated = SupportSession.objects.filter(pk=session.pk, status=Status.APPROVED).update(
        status=Status.ACTIVE, updated_at=timezone.now()
    )
    if not updated:
        return
    session.status = Status.ACTIVE
    _audit(
        "support.session.started",
        session,
        actor=getattr(request, "user", None),
        actor_type=ActorType.SUPPORT,
        request=request,
    )
    tenant = Tenant.objects.filter(pk=session.tenant_id).values_list("name", flat=True).first()
    _notify_owners(
        "support_session_started",
        {
            "tenant_name": tenant or "",
            "ticket_ref": session.ticket_ref,
            "ends_at": session.ends_at.strftime("%Y-%m-%d %H:%M UTC") if session.ends_at else "",
        },
    )


def expire_session(session_id: uuid.UUID) -> None:
    """A session whose window has passed: ``expired``, staff sign-ins on this host ended."""
    found = SupportSession.objects.select_for_update().filter(pk=session_id).first()
    if found is None or found.status not in SupportSession.OPEN_STATUSES:
        return
    if found.ends_at is not None and found.ends_at > timezone.now():
        return
    _close(found, Status.EXPIRED)
    _audit("support.session.expired", found, actor_type=ActorType.SYSTEM)


# --------------------------------------------------------------------------- D5 setting
@transaction.atomic
def set_approval_required(
    *, actor: User, required: bool, reason: str, request: HttpRequest | None = None
) -> bool:
    """D5: only an active tenant owner (who also holds ``tenancy.tenant.update``) changes the
    support-approval setting, with a reason. Step-up is enforced by the API (M8)."""
    from apps.tenancy.access import is_active_owner

    ctx: TenantContext = common.tenant_context()
    require_perm(actor, "tenancy.tenant.update", target=ScopeTarget(ctx.id), use_cache=False)
    if not is_active_owner(actor.pk):
        raise PermissionDenied("Only an owner of the organisation can change this setting.")
    cleaned = (reason or "").strip()
    if len(cleaned) < _REASON_MIN:
        raise ValidationError({"reason": "Explain the reason in at least 10 characters."})
    tenant = common.lock_tenant(ctx)
    old = _approval_required(tenant)
    if old == required:
        return old
    settings_value = dict(tenant.settings) if isinstance(tenant.settings, dict) else {}
    settings_value[APPROVAL_SETTING] = required
    Tenant.objects.filter(pk=tenant.pk).update(settings=settings_value, updated_at=timezone.now())
    bump_tenant_version(ctx.id)
    record(
        "tenancy.support_approval.changed",
        actor=actor,
        request=request,
        target_type="tenant",
        target_id=ctx.id,
        metadata={"old": old, "new": required, "reason": cleaned},
    )
    _notify_owners(
        "support_approval_changed",
        {"tenant_name": tenant.name, "required": required, "changed_by": actor.email},
    )
    return required
