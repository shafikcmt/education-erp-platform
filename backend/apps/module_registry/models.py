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
