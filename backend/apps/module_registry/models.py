"""Module registry (Phase 4 M1; ADR-050).

``Module`` is a global, code-defined catalogue shared by every tenant (no tenant data). The
runtime role may only read it; the owner-run bootstrap (``sync_modules``) writes it, as for
the permission catalogue (O1).
"""

from __future__ import annotations

from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.models import BaseModel


class Module(BaseModel):
    class Category(models.TextChoices):
        PLATFORM = "platform", "Platform"
        STANDARD = "standard", "Standard"
        EXTENSION = "extension", "Extension"

    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=16, choices=Category.choices)
    version = models.CharField(max_length=32)
    dependencies = ArrayField(models.CharField(max_length=64), default=list, blank=True)
    sellable = models.BooleanField(default=False)
    # False while only planned (no code installed): packageable, never entitled.
    available = models.BooleanField(default=False)
    deprecated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "module_registry_module"
        ordering = ("code",)

    def __str__(self) -> str:
        return self.code


class FeatureFlag(BaseModel):
    """Rollout control, separate from entitlements (ADR-053). ``rules``: ``percentage``
    (0-100, stable per tenant), ``plans`` (plan codes) and ``tenants`` (tenant ids)."""

    key = models.CharField(max_length=80, unique=True)
    description = models.CharField(max_length=255, blank=True, default="")
    default_enabled = models.BooleanField(default=False)
    rules = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "module_registry_featureflag"
        ordering = ("key",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(key__regex=r"^[a-z][a-z0-9_.]{2,79}$"),
                name="module_registry_flag_key_valid",
            )
        ]

    def __str__(self) -> str:
        return self.key


class ModuleOverride(BaseModel):
    """Super Admin grant or revocation of one module for one tenant (ADR-052), with a reason
    and an optional expiry. Per-tenant registry row: self-scoped, tenant-read-only RLS."""

    class Kind(models.TextChoices):
        GRANT = "grant", "Grant"
        REVOKE = "revoke", "Revoke"

    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.PROTECT, related_name="+")
    module = models.ForeignKey(Module, on_delete=models.PROTECT, to_field="code", related_name="+")
    kind = models.CharField(max_length=8, choices=Kind.choices)
    reason = models.CharField(max_length=200)
    expires_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "module_registry_override"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "module"],
                condition=models.Q(ended_at__isnull=True),
                name="module_registry_override_one_open",
            )
        ]
