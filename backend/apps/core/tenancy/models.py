"""``TenantScopedModel`` and its fail-closed manager (Phase 3 plan §8.1; ADR-009 §2).

* Every query through ``objects`` (and Django's base manager) is filtered by the bound tenant
  and raises :class:`TenantContextMissing` when there is none. There is no "all tenants"
  manager; platform code uses ``platform_scope`` mechanisms instead.
* ``save()`` takes ``tenant_id`` from the context and refuses a different one, so a row can be
  neither created in nor moved to another tenant. ``update()``, ``bulk_create()`` and
  ``bulk_update()`` apply the same rule.
* RLS (``EnableTenantRLS``) enforces the same boundary again in PostgreSQL.

M1 note: ``tenant_id`` is a plain indexed UUID column. M2 turns it into a foreign key to the
tenant registry (``tenancy.Tenant``, same column name) once that model exists.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any, TypeVar

from django.db import models

from apps.core.models import BaseModel
from apps.core.tenancy.context import require_tenant
from apps.core.tenancy.exceptions import TenantMismatch

_TENANT_FIELDS = frozenset({"tenant", "tenant_id"})

M = TypeVar("M", bound=BaseModel)


def _stamp(obj: Any) -> None:
    """Set/verify the row's tenant from the context (``TenantScopedModel`` instances only)."""
    obj._assign_current_tenant()


class TenantQuerySet(models.QuerySet[M]):
    def update(self, **kwargs: Any) -> int:
        if _TENANT_FIELDS & kwargs.keys():
            raise TenantMismatch("tenant_id can't be changed with update().")
        return super().update(**kwargs)

    def bulk_create(self, objs: Iterable[M], *args: Any, **kwargs: Any) -> list[M]:
        objs = list(objs)
        for obj in objs:
            _stamp(obj)
        return super().bulk_create(objs, *args, **kwargs)

    def bulk_update(
        self, objs: Iterable[M], fields: Iterable[str], batch_size: int | None = None
    ) -> int:
        fields = list(fields)
        if _TENANT_FIELDS & set(fields):
            raise TenantMismatch("tenant_id can't be changed with bulk_update().")
        objs = list(objs)
        for obj in objs:
            _stamp(obj)
        return super().bulk_update(objs, fields, batch_size=batch_size)


class TenantManager(models.Manager[M]):
    """Fail-closed: every queryset is filtered by the bound tenant, or raises."""

    def get_queryset(self) -> TenantQuerySet[M]:
        ctx = require_tenant()
        return TenantQuerySet(self.model, using=self._db).filter(tenant_id=ctx.id)


class TenantScopedModel(BaseModel):
    """Abstract base for every tenant-owned table (ADR-009 §1)."""

    tenant_id = models.UUIDField(db_index=True, editable=False)
    created_by = models.UUIDField(null=True, blank=True, editable=False)
    updated_by = models.UUIDField(null=True, blank=True, editable=False)

    objects = TenantManager()

    class Meta:
        abstract = True
        ordering = ("-created_at",)
        # Django's internal lookups (related access, refresh_from_db, deletion) go through the
        # base manager: make it fail closed too.
        base_manager_name = "objects"

    def _assign_current_tenant(self) -> uuid.UUID:
        ctx = require_tenant()
        if self.tenant_id is None:
            self.tenant_id = ctx.id
        elif self.tenant_id != ctx.id:
            raise TenantMismatch("Row belongs to a different tenant than the current context.")
        return ctx.id

    def save(self, *args: Any, **kwargs: Any) -> None:
        self._assign_current_tenant()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and _TENANT_FIELDS & set(update_fields):
            raise TenantMismatch("tenant_id can't be changed.")
        super().save(*args, **kwargs)

    def refresh_from_db(self, *args: Any, **kwargs: Any) -> None:
        self._assign_current_tenant()  # never reload a row outside its tenant
        super().refresh_from_db(*args, **kwargs)
