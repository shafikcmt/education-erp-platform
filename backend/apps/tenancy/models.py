"""Tenancy data model (Phase 3 M2; plan §4.1, §4.4; ADR-010, ADR-044, ADR-046).

* ``Tenant`` is the **platform registry** (no ``tenant_id``). Its table has a self-scoping RLS
  policy: a tenant context sees only its own row, the platform (no context) sees all.
* Every other model is tenant-owned (``TenantScopedModel``, standard RLS).
* Foreign keys **between tenant tables** use ``db_constraint=False``: the only database
  constraint is the composite ``(tenant_id, …)`` key added in ``tenancy.0002`` (§4.4). FK checks
  bypass RLS, so a single-column key would accept another tenant's id and reveal whether it
  exists; the composite key rejects every foreign id the same way.

Behaviour (memberships, invitations, support sessions) arrives with M4/M5; M2 provides the
schema, constraints, RLS, registry rules (slug, lifecycle, limits) and the definer functions.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models.functions import Lower

from apps.core.models import BaseModel
from apps.core.tenancy.context import TenantContext
from apps.core.tenancy.models import TenantScopedModel
from apps.tenancy.rules import (
    DOMAIN_PATTERN,
    NUMERIC_HOST_PATTERN,
    RESERVED_SLUGS,
    SLUG_PATTERN,
    InvalidSlug,
    TenantStatus,
    check_transition,
    default_limits,
    default_tenant_settings,
    validate_slug,
)

INSTITUTION_TYPES = (
    ("school", "School"),
    ("college", "College"),
    ("university", "University"),
    ("madrasa", "Madrasa"),
    ("coaching_center", "Coaching center"),
    ("training_institute", "Training institute"),
)


class ScopeType(models.TextChoices):
    TENANT = "tenant", "Tenant"
    INSTITUTION = "institution", "Institution"
    CAMPUS = "campus", "Campus"


def _scope_consistent(prefix: str = "") -> models.Q:
    """``tenant`` → no institution/campus; ``institution`` → institution only; ``campus`` → both.

    With ``MATCH SIMPLE`` composite keys this makes the right key mandatory (plan §4.4 (3)).
    """
    inst, campus = f"{prefix}institution__isnull", f"{prefix}campus__isnull"
    return (
        models.Q(scope_type=ScopeType.TENANT, **{inst: True, campus: True})
        | models.Q(scope_type=ScopeType.INSTITUTION, **{inst: False, campus: True})
        | models.Q(scope_type=ScopeType.CAMPUS, **{inst: False, campus: False})
    )


# --------------------------------------------------------------------------- registry
class Tenant(BaseModel):
    """A customer organisation (platform registry; self-scoped RLS)."""

    slug = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=200)
    status = models.CharField(
        max_length=16, choices=TenantStatus.CHOICES, default=TenantStatus.PROVISIONING
    )
    default_locale = models.CharField(max_length=10, default="en")
    locales = ArrayField(models.CharField(max_length=10), default=list, blank=True)
    timezone = models.CharField(max_length=64, default="UTC")
    currency = models.CharField(max_length=3, default="USD")
    country = models.CharField(max_length=2, blank=True, default="")
    data_region = models.CharField(max_length=32, blank=True, default="")
    limits = models.JSONField(default=default_limits)
    limits_overridden_by = models.UUIDField(null=True, blank=True)
    limits_overridden_at = models.DateTimeField(null=True, blank=True)
    limits_override_reason = models.CharField(max_length=200, blank=True, default="")
    settings = models.JSONField(default=default_tenant_settings)
    branding = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "tenancy_tenant"
        ordering = ("name",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(slug__regex=SLUG_PATTERN)
                & ~models.Q(slug__contains="--")
                & ~models.Q(slug__in=sorted(RESERVED_SLUGS)),
                name="tenancy_tenant_slug_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=[c for c, _ in TenantStatus.CHOICES]),
                name="tenancy_tenant_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.slug

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self._state.adding:
            validate_slug(self.slug)
        else:
            stored = type(self).objects.filter(pk=self.pk).values_list("slug", "status").first()
            if stored is not None:
                if stored[0] != self.slug:
                    raise InvalidSlug("A tenant slug can never change.", code="slug_immutable")
                if stored[1] != self.status:
                    check_transition(stored[1], self.status)
        super().save(*args, **kwargs)

    def as_context(self) -> TenantContext:
        return TenantContext(id=self.id, slug=self.slug, status=self.status)


# --------------------------------------------------------------------------- tenant-owned
class TenantDomain(TenantScopedModel):
    """Host name of a tenant (``{slug}.<platform-domain>``; custom domains later, ADR-027)."""

    class Kind(models.TextChoices):
        SUBDOMAIN = "subdomain", "Subdomain"
        CUSTOM = "custom", "Custom domain"

    domain = models.CharField(max_length=253, unique=True)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.SUBDOMAIN)
    is_primary = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "tenancy_tenantdomain"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"],
                condition=models.Q(is_primary=True),
                name="tenancy_domain_one_primary",
            ),
            models.CheckConstraint(
                condition=models.Q(domain__regex=DOMAIN_PATTERN)
                & ~models.Q(domain__regex=NUMERIC_HOST_PATTERN),
                name="tenancy_domain_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.domain


class Institution(TenantScopedModel):
    institution_type = models.CharField(max_length=32, choices=INSTITUTION_TYPES)
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=200)
    name_i18n = models.JSONField(default=dict, blank=True)
    preset_code = models.CharField(max_length=64, blank=True, default="")
    preset_version = models.CharField(max_length=32, blank=True, default="")
    settings = models.JSONField(default=dict, blank=True)
    extra = models.JSONField(default=dict, blank=True)  # custom field values (Phase 5 M6)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "tenancy_institution"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="tenancy_inst_code_unique"),
            models.UniqueConstraint(fields=["tenant", "id"], name="tenancy_inst_tenant_key"),
        ]

    def __str__(self) -> str:
        return self.code


class Campus(TenantScopedModel):
    institution = models.ForeignKey(
        Institution, on_delete=models.PROTECT, related_name="campuses", db_constraint=False
    )
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=200)
    name_i18n = models.JSONField(default=dict, blank=True)
    address = models.JSONField(default=dict, blank=True)
    timezone = models.CharField(max_length=64, blank=True, default="")
    is_main = models.BooleanField(default=False)
    extra = models.JSONField(default=dict, blank=True)  # custom field values (Phase 5 M6)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "tenancy_campus"
        verbose_name_plural = "campuses"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "institution", "code"], name="tenancy_campus_code_unique"
            ),
            models.UniqueConstraint(
                fields=["tenant", "institution"],
                condition=models.Q(is_main=True),
                name="tenancy_campus_one_main",
            ),
            models.UniqueConstraint(
                fields=["tenant", "institution", "id"], name="tenancy_campus_tenant_key"
            ),
        ]

    def __str__(self) -> str:
        return self.code


class Membership(TenantScopedModel):
    class Status(models.TextChoices):
        INVITED = "invited", "Invited"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        LEFT = "left", "Left"

    # DO_NOTHING for references from tenant tables to platform tables (user, role): platform
    # deletions must not walk tenant tables through the fail-closed manager. The database
    # enforces integrity (plain FK here; composite RESTRICT key for roles, tenancy.0002).
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DO_NOTHING, related_name="memberships"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.INVITED)
    invited_by = models.UUIDField(null=True, blank=True)
    joined_at = models.DateTimeField(null=True, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "tenancy_membership"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "user"], name="tenancy_member_unique"),
            models.UniqueConstraint(fields=["tenant", "id"], name="tenancy_member_tenant_key"),
        ]

    def __str__(self) -> str:
        return f"membership {self.pk}"


class Invitation(TenantScopedModel):
    email = models.EmailField(max_length=254)
    role = models.ForeignKey(
        "rbac.Role", on_delete=models.DO_NOTHING, related_name="+", db_constraint=False
    )
    scope_type = models.CharField(max_length=16, choices=ScopeType.choices)
    institution = models.ForeignKey(
        Institution,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
        db_constraint=False,
    )
    campus = models.ForeignKey(
        Campus,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
        db_constraint=False,
    )
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.UUIDField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "tenancy_invitation"
        constraints = [
            models.CheckConstraint(condition=_scope_consistent(), name="tenancy_invite_scope"),
            models.CheckConstraint(
                condition=models.Q(email=Lower("email")), name="tenancy_invite_email_lower"
            ),
            models.UniqueConstraint(
                fields=["tenant", "email", "role", "scope_type", "institution", "campus"],
                condition=models.Q(accepted_at__isnull=True, revoked_at__isnull=True),
                nulls_distinct=False,
                name="tenancy_invite_one_open",
            ),
        ]

    def __str__(self) -> str:
        return f"invitation {self.pk}"


class SupportSession(TenantScopedModel):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved"
        ACTIVE = "active", "Active"
        ENDED = "ended", "Ended"
        REVOKED = "revoked", "Revoked"
        EXPIRED = "expired", "Expired"
        REJECTED = "rejected", "Rejected"

    OPEN_STATUSES = (Status.REQUESTED, Status.APPROVED, Status.ACTIVE)

    staff_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DO_NOTHING, related_name="+"
    )
    reason = models.TextField()
    ticket_ref = models.CharField(max_length=64)
    access_level = models.CharField(
        max_length=16, choices=[("read_only", "Read only")], default="read_only"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.REQUESTED)
    requested_at = models.DateTimeField()
    approved_by = models.UUIDField(null=True, blank=True)
    # Requested length (15-120 minutes, plan §11.1). The window starts at approval.
    duration_minutes = models.PositiveSmallIntegerField(default=60)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.UUIDField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "tenancy_supportsession"
        constraints = [
            # 15-120 minutes (plan §11.1).
            models.CheckConstraint(
                condition=models.Q(starts_at__isnull=True)
                | models.Q(ends_at__isnull=True)
                | (
                    models.Q(ends_at__gte=models.F("starts_at") + timedelta(minutes=15))
                    & models.Q(ends_at__lte=models.F("starts_at") + timedelta(minutes=120))
                ),
                name="tenancy_support_duration",
            ),
            models.CheckConstraint(
                condition=models.Q(access_level="read_only"), name="tenancy_support_read_only"
            ),
            models.CheckConstraint(
                condition=models.Q(duration_minutes__gte=15, duration_minutes__lte=120),
                name="tenancy_support_requested_duration",
            ),
            models.UniqueConstraint(
                fields=["tenant", "staff_user"],
                condition=models.Q(status__in=["requested", "approved", "active"]),
                name="tenancy_support_one_open",
            ),
        ]

    def __str__(self) -> str:
        return f"support session {self.pk}"


# --------------------------------------------------------------------------- self-service sign-up
class SignupStatus(models.TextChoices):
    PENDING = "pending", "Waiting for email verification"
    VERIFIED = "verified", "Waiting for approval"
    PROVISIONING = "provisioning", "Being provisioned"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    EXPIRED = "expired", "Expired"


class SignupRequest(BaseModel):
    """A prospective organisation's sign-up (Phase 5 M8, P23; ADR-060 Q3).

    Platform registry table: no tenant exists yet. Only the hash of the verification token is
    stored. Every request needs a platform administrator's approval before a tenant is
    provisioned (P4). Closed requests are deleted after the retention period.
    """

    email = models.EmailField(max_length=254)
    organisation_name = models.CharField(max_length=200)
    slug = models.CharField(max_length=32)
    institution_type = models.CharField(max_length=32)
    institution_name = models.CharField(max_length=200)
    default_locale = models.CharField(max_length=8)
    timezone = models.CharField(max_length=64)
    currency = models.CharField(max_length=3)
    country = models.CharField(max_length=2, blank=True)
    status = models.CharField(
        max_length=16, choices=SignupStatus.choices, default=SignupStatus.PENDING
    )
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decision_reason = models.CharField(max_length=200, blank=True)
    # Not named ``tenant``: a ``tenant_id`` column marks tenant-owned rows for the isolation
    # gates, and this registry row is not tenant data.
    provisioned_tenant = models.ForeignKey(
        Tenant, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        indexes = [models.Index(fields=["status", "created_at"])]
