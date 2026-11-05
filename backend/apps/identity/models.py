"""Custom user model (minimal stub, approved for Phase 1).

Deliberately small: authentication flows, MFA, memberships and RBAC are Phase 2/3 work.
Tenant membership lives in a separate ``Membership`` model (one account, many tenants), so
``User`` itself is a platform-level table, not tenant-scoped.
"""

from typing import ClassVar

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models.functions import Lower

from apps.core.models import BaseModel
from apps.identity.managers import UserManager


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(max_length=254, unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(
        default=False, help_text="Platform staff with Django admin access. Not a tenant role."
    )

    objects: ClassVar[UserManager] = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        db_table = "identity_user"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(Lower("email"), name="identity_user_email_ci_unique"),
        ]

    def __str__(self) -> str:
        return self.email

    def clean(self) -> None:
        super().clean()
        self.email = UserManager.normalize_email_address(self.email)
