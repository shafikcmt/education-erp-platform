"""Business authorization data (ADR-033): permissions, roles, role permissions, platform roles.

* ``Role`` and ``RolePermission`` are **dual-scope** tables (plan §4.6): ``tenant_id`` is NULL
  for platform roles and system templates, and holds the tenant for Phase 3 tenant roles.
  ``RolePermission.tenant_id`` is kept equal to its role's ``tenant_id`` by a trigger, so Phase 3
  RLS needs no backfill.
* ``Permission`` and ``PlatformRoleAssignment`` are platform tables (no tenant data).
* Django's ``auth.Permission``/``auth.Group`` are never used for application checks.
"""

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.models import BaseModel
from apps.core.tenancy.models import TenantScopedModel


class Permission(BaseModel):
    code = models.CharField(max_length=100, unique=True)
    module_code = models.CharField(max_length=50)
    description = models.CharField(max_length=255)
    is_sensitive = models.BooleanField(default=False)
    requires_mfa = models.BooleanField(default=False)
    requires_step_up = models.BooleanField(default=False)
    deprecated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "rbac_permission"
        ordering = ("code",)

    def __str__(self) -> str:
        return self.code


class RoleKind(models.TextChoices):
    PLATFORM = "platform", "Platform role"
    TEMPLATE = "template", "Tenant role template"
    TENANT = "tenant", "Tenant role"


class Role(BaseModel):
    tenant_id = models.UUIDField(null=True, blank=True)
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=120)
    name_i18n = models.JSONField(default=dict, blank=True)
    description = models.CharField(max_length=255, blank=True, default="")
    kind = models.CharField(max_length=16, choices=RoleKind.choices)
    institution_types = ArrayField(models.CharField(max_length=32), default=list, blank=True)
    is_system = models.BooleanField(default=False)
    # Tenant system copies point at the template they mirror (Phase 3 M4; plan §4.1, Q5).
    # A trigger guarantees the target is a ``template`` row; clones and custom roles have none.
    template = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="copies"
    )
    permissions: "models.ManyToManyField[Permission, RolePermission]" = models.ManyToManyField(
        Permission, through="RolePermission", related_name="roles"
    )

    class Meta:
        db_table = "rbac_role"
        ordering = ("kind", "code")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "code"],
                name="rbac_role_tenant_code_unique",
                nulls_distinct=False,
            ),
            # Composite-FK target (Phase 3 plan §4.4): tenant tables reference tenant roles by
            # (tenant_id, id), so a role of another tenant (or a template) never matches.
            models.UniqueConstraint(fields=["tenant_id", "id"], name="rbac_role_tenant_key"),
            models.CheckConstraint(
                condition=models.Q(kind="tenant", tenant_id__isnull=False)
                | models.Q(kind__in=["platform", "template"], tenant_id__isnull=True),
                name="rbac_role_kind_tenant_consistent",
            ),
            # Only a tenant's read-only system copy mirrors a template; one copy per template.
            models.CheckConstraint(
                condition=models.Q(template__isnull=True) | models.Q(kind="tenant", is_system=True),
                name="rbac_role_template_only_on_system_copy",
            ),
            models.UniqueConstraint(
                fields=["tenant_id", "template"],
                condition=models.Q(template__isnull=False),
                name="rbac_role_one_copy_per_template",
            ),
        ]

    def __str__(self) -> str:
        return self.code


class RolePermission(BaseModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(
        Permission, on_delete=models.PROTECT, related_name="role_permissions"
    )
    # Mirrors role.tenant_id (set by trigger rbac_rolepermission_tenant_sync).
    tenant_id = models.UUIDField(null=True, blank=True, editable=False)

    class Meta:
        db_table = "rbac_rolepermission"
        constraints = [
            models.UniqueConstraint(
                fields=["role", "permission"], name="rbac_rolepermission_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.role_id}:{self.permission_id}"


class PlatformRoleAssignment(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="platform_roles"
    )
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="platform_assignments")
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    granted_at = models.DateTimeField()
    reason = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "rbac_platformroleassignment"
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="rbac_platformrole_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.role_id}"


class AssignmentScope(models.TextChoices):
    TENANT = "tenant", "Tenant"
    INSTITUTION = "institution", "Institution"
    CAMPUS = "campus", "Campus"


class RoleAssignment(TenantScopedModel):
    """A tenant role held by a member in a scope (Phase 3 M4; plan §4.1, §9; ADR-044).

    Tenant-owned (standard RLS). References to the membership, role, institution and campus
    are composite ``(tenant_id, ...)`` keys in the database (``rbac.0005``), so a row of another
    tenant, a template role or a campus of another institution can never be referenced. The
    relations to ``tenancy`` models are lazy strings: ``rbac`` never imports ``tenancy``.

    An assignment is in force while it is not revoked and ``valid_from <= now < valid_until``.
    Rows are never deleted: revoking sets ``revoked_at`` (history and audit stay intact).
    """

    membership = models.ForeignKey(
        "tenancy.Membership",
        on_delete=models.PROTECT,
        related_name="role_assignments",
        db_constraint=False,
    )
    role = models.ForeignKey(
        Role, on_delete=models.DO_NOTHING, related_name="assignments", db_constraint=False
    )
    scope_type = models.CharField(max_length=16, choices=AssignmentScope.choices)
    institution = models.ForeignKey(
        "tenancy.Institution",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
        db_constraint=False,
    )
    campus = models.ForeignKey(
        "tenancy.Campus",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
        db_constraint=False,
    )
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(null=True, blank=True)
    granted_by = models.UUIDField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True, default="")
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.UUIDField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "rbac_roleassignment"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(scope_type="tenant", institution__isnull=True, campus__isnull=True)
                    | models.Q(
                        scope_type="institution", institution__isnull=False, campus__isnull=True
                    )
                    | models.Q(scope_type="campus", institution__isnull=False, campus__isnull=False)
                ),
                name="rbac_assignment_scope",
            ),
            models.CheckConstraint(
                condition=models.Q(valid_until__isnull=True)
                | models.Q(valid_until__gt=models.F("valid_from")),
                name="rbac_assignment_validity",
            ),
            # No duplicate live assignment of the same role in the same scope.
            models.UniqueConstraint(
                fields=["tenant", "membership", "role", "scope_type", "institution", "campus"],
                condition=models.Q(revoked_at__isnull=True),
                nulls_distinct=False,
                name="rbac_assignment_one_live",
            ),
        ]

    def __str__(self) -> str:
        return f"assignment {self.pk}"
