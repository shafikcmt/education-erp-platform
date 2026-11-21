"""Tenant registry operations of platform staff (Phase 3 M8; plan §6.3 P4, P5; ADR-010, D2).

Every function runs on the **platform host**, outside any tenant context, inside
``platform_scope`` with the exact catalogued permission (checked again there, uncached):

* **P4 provisioning** (``tenancy.tenant.create``): the registry row is inserted first
  (mechanism R, status ``provisioning``, so its host does not resolve yet). One targeted tenant
  transaction (mechanism T) then creates the subdomain, the system role copies, the first
  institution and its main campus and the owner invitation, and activates the tenant. If that
  transaction fails, nothing of it remains and the registry row is marked ``deleted`` (the
  slug stays tombstoned). Refused while tenant hosts are disabled where the settings require
  them (production, D1).
* **P5 registry changes** (``update_any``, ``suspend``, ``limit.override``): registry fields
  only (never ``settings`` or tenant data). Each change is written to the platform log and,
  in a targeted tenant transaction, to the tenant's own log. Suspension also revokes every
  open support session of the tenant (D2) in that transaction.

Reasons (at least 10 characters) are required for suspension, reactivation and limit
overrides; step-up is enforced by the API (the permissions require it).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from apps.audit.services import record
from apps.core.tenancy import tenant_atomic
from apps.core.tenancy.platform import platform_scope
from apps.rbac.engine import bump_tenant_version
from apps.rbac.role_templates import TENANT_OWNER
from apps.rbac.tenant_roles import sync_system_copies, system_role
from apps.tenancy.errors import TenantHostsDisabled
from apps.tenancy.models import Campus, Institution, Invitation, Tenant, TenantDomain
from apps.tenancy.rules import LIMIT_KEYS, TenantStatus, check_transition, validate_slug
from apps.tenancy.services import support as support_services
from apps.tenancy.services.invitations import issue_invitation

if TYPE_CHECKING:
    from django.http import HttpRequest

    from apps.identity.models import User

logger = structlog.get_logger("erp.tenancy")

CREATE = "tenancy.tenant.create"
UPDATE_ANY = "tenancy.tenant.update_any"
SUSPEND = "tenancy.tenant.suspend"
OVERRIDE = "tenancy.limit.override"
REGISTRY_FIELDS = ("name", "default_locale", "locales", "timezone", "currency", "country")
_REASON_MIN = 10
_MAX_LIMIT = 10_000


@dataclass(frozen=True)
class FirstInstitution:
    institution_type: str
    code: str
    name: str
    campus_code: str = "main"
    campus_name: str = "Main campus"


def _reason(reason: str) -> str:
    cleaned = (reason or "").strip()
    if not _REASON_MIN <= len(cleaned) <= 200:
        raise ValidationError({"reason": "Explain the reason in 10 to 200 characters."})
    return cleaned


def tenant_domain(slug: str) -> str:
    return f"{slug}.{settings.TENANT_BASE_DOMAIN}"


def _assert_provisioning_allowed() -> None:
    if not settings.TENANT_BASE_DOMAIN or (
        settings.TENANT_PROVISIONING_REQUIRES_HOSTS and not settings.TENANT_HOSTS_ENABLED
    ):
        raise TenantHostsDisabled()


def _platform_log(
    action: str,
    tenant: Tenant,
    *,
    actor: User,
    request: HttpRequest | None,
    metadata: dict[str, Any],
) -> None:
    """The platform log (no tenant context): the registry change with the tenant id as metadata."""
    record(
        action,
        actor=actor,
        request=request,
        target_type="tenant",
        target_id=tenant.pk,
        metadata={**metadata, "tenant_id": str(tenant.pk)},
    )


# --------------------------------------------------------------------------- P4
def provision_tenant(
    *,
    actor: User,
    slug: str,
    name: str,
    owner_email: str,
    institution: FirstInstitution,
    default_locale: str = "en",
    locales: list[str] | None = None,
    timezone_name: str = "UTC",
    currency: str = "USD",
    country: str = "",
    request: HttpRequest | None = None,
) -> Tenant:
    _assert_provisioning_allowed()
    validate_slug(slug)
    locales = locales or [default_locale]
    if default_locale not in locales:
        raise ValidationError({"default_locale": "Must be one of the enabled languages."})
    with platform_scope(operation="P4", actor=actor, reason=f"provision tenant {slug}"):
        try:
            with transaction.atomic():
                tenant = Tenant.objects.create(
                    slug=slug,
                    name=name,
                    default_locale=default_locale,
                    locales=locales,
                    timezone=timezone_name,
                    currency=currency,
                    country=country,
                )
        except IntegrityError:
            raise ValidationError({"slug": "This name is not available."}) from None
        try:
            with tenant_atomic(tenant.as_context()):
                _provision_contents(tenant, actor, owner_email, institution, request)
        except Exception as exc:
            _mark_failed(tenant, actor, request, exc)
            raise
        tenant.refresh_from_db()
        for hook in getattr(settings, "TENANCY_PROVISIONING_HOOKS", []):
            import_string(hook)(tenant, actor, request)  # e.g. the trial plan (Phase 4)
        _platform_log(
            "tenancy.tenant.provisioned",
            tenant,
            actor=actor,
            request=request,
            metadata={"slug": slug},
        )
    return tenant


def _provision_contents(
    tenant: Tenant,
    actor: User,
    owner_email: str,
    first: FirstInstitution,
    request: HttpRequest | None,
) -> None:
    now = timezone.now()
    # Subdomains of the platform's own base domain are verified by construction.
    TenantDomain.objects.create(domain=tenant_domain(tenant.slug), is_primary=True, verified_at=now)
    sync_system_copies(tenant.pk)
    institution = Institution.objects.create(
        code=first.code, name=first.name, institution_type=first.institution_type
    )
    Campus.objects.create(
        institution=institution, code=first.campus_code, name=first.campus_name, is_main=True
    )
    issue_invitation(
        actor=actor,
        email=owner_email,
        role=system_role(tenant.pk, TENANT_OWNER),
        scope_type="tenant",
        request=request,
    )
    locked = Tenant.objects.select_for_update().get(pk=tenant.pk)
    locked.status = TenantStatus.ACTIVE
    locked.save(update_fields=["status", "updated_at"])
    record(
        "tenancy.tenant.provisioned",
        actor=actor,
        request=request,
        target_type="tenant",
        target_id=tenant.pk,
        metadata={"slug": tenant.slug},
    )


def _mark_failed(tenant: Tenant, actor: User, request: HttpRequest | None, exc: Exception) -> None:
    """Compensation: the tenant transaction rolled back; tombstone the registry row."""
    try:
        Tenant.objects.filter(pk=tenant.pk, status=TenantStatus.PROVISIONING).update(
            status=TenantStatus.DELETED, updated_at=timezone.now()
        )
        record(
            "tenancy.tenant.provisioning_failed",
            outcome="failure",
            actor=actor,
            request=request,
            target_type="tenant",
            target_id=tenant.pk,
            metadata={
                "slug": tenant.slug,
                "tenant_id": str(tenant.pk),
                "error": type(exc).__name__,
            },
        )
    except Exception:
        logger.exception("tenancy.provisioning_cleanup_failed", tenant_id=str(tenant.pk))


def resend_owner_invitation(
    *, actor: User, tenant_id: uuid.UUID, email: str, request: HttpRequest | None = None
) -> Invitation:
    """Send (or replace) the owner invitation of a tenant (P4). Open owner invitations to
    other addresses stay valid; one to the same address is replaced."""
    with platform_scope(operation="P4", actor=actor, reason="send owner invitation"):
        tenant = _registry_row(tenant_id)
        if tenant.status != TenantStatus.ACTIVE:
            raise ValidationError({"tenant": "Only an active tenant can get owner invitations."})
        with tenant_atomic(tenant.as_context()):
            owner = system_role(tenant.pk, TENANT_OWNER)
            address = (email or "").strip().lower()
            Invitation.objects.filter(
                email=address,
                role=owner,
                scope_type="tenant",
                accepted_at__isnull=True,
                revoked_at__isnull=True,
            ).update(revoked_at=timezone.now(), updated_at=timezone.now())
            invitation, _ = issue_invitation(
                actor=actor, email=address, role=owner, scope_type="tenant", request=request
            )
            record(
                "tenancy.tenant.owner_invited",
                actor=actor,
                request=request,
                target_type="tenant",
                target_id=tenant.pk,
                metadata={"tenant_id": str(tenant.pk)},
            )
        _platform_log(
            "tenancy.tenant.owner_invited", tenant, actor=actor, request=request, metadata={}
        )
    return invitation


# --------------------------------------------------------------------------- P5
def _registry_row(tenant_id: Any) -> Tenant:
    tenant = Tenant.objects.filter(pk=tenant_id).exclude(status=TenantStatus.DELETED).first()
    if tenant is None:
        raise ValidationError({"tenant": "Unknown tenant."})
    return tenant


def _tenant_log(
    tenant: Tenant,
    action: str,
    *,
    actor: User,
    request: HttpRequest | None,
    metadata: dict[str, Any],
    then: Any = None,
) -> Any:
    """Write ``action`` to the tenant's log in a targeted tenant transaction (mechanism T);
    ``then`` runs in the same transaction."""
    with tenant_atomic(tenant.as_context()):
        result = then() if then is not None else None
        record(
            action,
            actor=actor,
            request=request,
            target_type="tenant",
            target_id=tenant.pk,
            metadata={**metadata, "tenant_id": str(tenant.pk)},
        )
        bump_tenant_version(tenant.pk)
        return result


def update_registry(
    *, actor: User, tenant_id: uuid.UUID, changes: dict[str, Any], request: HttpRequest | None
) -> Tenant:
    with platform_scope(
        operation="P5", actor=actor, reason="update tenant registry", permission=UPDATE_ANY
    ):
        tenant = _registry_row(tenant_id)
        fields = []
        for key, value in changes.items():
            if key not in REGISTRY_FIELDS:
                raise ValidationError({key: "This field can't be changed here."})
            if getattr(tenant, key) != value:
                setattr(tenant, key, value)
                fields.append(key)
        if tenant.locales and tenant.default_locale not in tenant.locales:
            raise ValidationError({"default_locale": "Must be one of the enabled languages."})
        if not fields:
            return tenant
        with transaction.atomic():
            tenant.save(update_fields=[*fields, "updated_at"])
        metadata = {"fields": ",".join(sorted(fields))}
        _tenant_log(
            tenant, "tenancy.tenant.updated", actor=actor, request=request, metadata=metadata
        )
        _platform_log(
            "tenancy.tenant.updated", tenant, actor=actor, request=request, metadata=metadata
        )
    return tenant


def _set_status(tenant: Tenant, status: str) -> None:
    check_transition(tenant.status, status)
    tenant.status = status
    with transaction.atomic():
        tenant.save(update_fields=["status", "updated_at"])


def suspend_tenant(
    *, actor: User, tenant_id: uuid.UUID, reason: str, request: HttpRequest | None = None
) -> Tenant:
    """Active → suspended. In the tenant's own transaction, every open support session is
    revoked (D2); members are refused from the next request (the gate checks the status on
    every request), and only owners can still sign in (restricted mode)."""
    cleaned = _reason(reason)
    with platform_scope(operation="P5", actor=actor, reason=cleaned, permission=SUSPEND):
        tenant = _registry_row(tenant_id)
        if tenant.status != TenantStatus.ACTIVE:
            raise ValidationError({"tenant": "Only an active tenant can be suspended."})
        _set_status(tenant, TenantStatus.SUSPENDED)
        revoked = _tenant_log(
            tenant,
            "tenancy.tenant.suspended",
            actor=actor,
            request=request,
            metadata={"reason": cleaned},
            then=lambda: support_services.revoke_open_sessions(reason="tenant_suspended"),
        )
        _platform_log(
            "tenancy.tenant.suspended",
            tenant,
            actor=actor,
            request=request,
            metadata={"reason": cleaned, "revoked_support_count": revoked},
        )
    return tenant


def reactivate_tenant(
    *, actor: User, tenant_id: uuid.UUID, reason: str, request: HttpRequest | None = None
) -> Tenant:
    """Suspended → active (the single reactivation path, M2 review)."""
    cleaned = _reason(reason)
    with platform_scope(operation="P5", actor=actor, reason=cleaned, permission=SUSPEND):
        tenant = _registry_row(tenant_id)
        if tenant.status != TenantStatus.SUSPENDED:
            raise ValidationError({"tenant": "Only a suspended tenant can be reactivated."})
        _set_status(tenant, TenantStatus.ACTIVE)
        metadata = {"reason": cleaned}
        _tenant_log(
            tenant, "tenancy.tenant.reactivated", actor=actor, request=request, metadata=metadata
        )
        _platform_log(
            "tenancy.tenant.reactivated", tenant, actor=actor, request=request, metadata=metadata
        )
    return tenant


def override_limits(
    *,
    actor: User,
    tenant_id: uuid.UUID,
    limits: dict[str, int],
    reason: str,
    request: HttpRequest | None = None,
) -> Tenant:
    """ADR-010 audited override of ``max_institutions`` / ``max_campuses``. Lowering a limit
    below the current count blocks new creations only; nothing existing is archived."""
    cleaned = _reason(reason)
    if set(limits) != set(LIMIT_KEYS) or not all(
        isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= _MAX_LIMIT
        for v in limits.values()
    ):
        raise ValidationError({"limits": f"Give {', '.join(LIMIT_KEYS)} as whole numbers ≥ 1."})
    with platform_scope(operation="P5", actor=actor, reason=cleaned, permission=OVERRIDE):
        tenant = _registry_row(tenant_id)
        tenant.limits = {**(tenant.limits if isinstance(tenant.limits, dict) else {}), **limits}
        tenant.limits_overridden_by = actor.pk
        tenant.limits_overridden_at = timezone.now()
        tenant.limits_override_reason = cleaned
        with transaction.atomic():
            tenant.save(
                update_fields=[
                    "limits",
                    "limits_overridden_by",
                    "limits_overridden_at",
                    "limits_override_reason",
                    "updated_at",
                ]
            )
        metadata = {"reason": cleaned, **limits}
        _tenant_log(
            tenant,
            "tenancy.tenant.limits_overridden",
            actor=actor,
            request=request,
            metadata=metadata,
        )
        _platform_log(
            "tenancy.tenant.limits_overridden",
            tenant,
            actor=actor,
            request=request,
            metadata=metadata,
        )
    return tenant
