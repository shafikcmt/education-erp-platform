"""User manager: email is the login identifier and is stored lower-cased."""

from typing import TYPE_CHECKING, Any

from django.contrib.auth.base_user import BaseUserManager

if TYPE_CHECKING:
    from apps.identity.models import User


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    @staticmethod
    def normalize_email_address(email: str) -> str:
        return email.strip().lower()

    def _create_user(self, email: str, password: str | None, **extra: Any) -> "User":
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=self.normalize_email_address(email), **extra)
        user.set_password(password)  # None -> unusable password (e.g. invited users)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> "User":
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> "User":
        """Platform staff superuser (Django admin / ops only — not a tenant role)."""
        extra["is_staff"] = True
        extra["is_superuser"] = True
        if not password:
            raise ValueError("Superusers must have a password.")
        return self._create_user(email, password, **extra)
