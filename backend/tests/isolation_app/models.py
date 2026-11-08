"""Probe models for the tenant-isolation tests (tests only)."""

from django.db import models

from apps.core.models import BaseModel
from apps.core.tenancy.models import TenantScopedModel


class ProbeRecord(TenantScopedModel):
    """Standard tenant table: ``EnableTenantRLS``."""

    name = models.CharField(max_length=64)

    class Meta(TenantScopedModel.Meta):
        db_table = "isolation_probe_record"

    def __str__(self) -> str:
        return self.name


class DualScopeProbe(BaseModel):
    """Platform rows (NULL tenant) visible to every tenant: ``EnableDualScopeRLS``."""

    tenant_id = models.UUIDField(null=True, blank=True)
    name = models.CharField(max_length=64)

    class Meta:
        db_table = "isolation_probe_dual"

    def __str__(self) -> str:
        return self.name


class PrivateDualScopeProbe(BaseModel):
    """Platform and tenant rows invisible to each other: ``EnableDualScopeRLS(private=True)``."""

    tenant_id = models.UUIDField(null=True, blank=True)
    name = models.CharField(max_length=64)

    class Meta:
        db_table = "isolation_probe_dual_private"

    def __str__(self) -> str:
        return self.name
