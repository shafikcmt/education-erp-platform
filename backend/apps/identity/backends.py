"""Authentication backend: Django's ``ModelBackend`` with two hardening changes (plan §6.1).

1. Unactivated accounts (``activated_at`` is NULL) can't authenticate.
2. Equal timing: Django already hashes a dummy password for unknown users; this backend does the
   same for accounts with an unusable password (unactivated/invited), which Django would reject
   without hashing, revealing that the account exists.
"""

from typing import Any

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.hashers import make_password
from django.http import HttpRequest

from apps.identity.models import User


class EmailBackend(ModelBackend):
    def authenticate(
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ) -> User | None:
        if username is None or password is None:
            return None
        try:
            user = User._default_manager.get(email__iexact=str(username).strip())
        except User.DoesNotExist:
            make_password(password)  # equal timing for unknown emails
            return None
        if not user.has_usable_password():
            make_password(password)  # equal timing for unactivated accounts
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    def user_can_authenticate(self, user: Any) -> bool:
        return bool(super().user_can_authenticate(user) and user.activated_at is not None)
