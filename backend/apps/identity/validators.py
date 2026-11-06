"""Password validators plugged into Django's ``AUTH_PASSWORD_VALIDATORS`` (plan §6.3)."""

import hashlib
import urllib.error
import urllib.request
from typing import Any

import structlog
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

logger = structlog.get_logger("erp.identity")


class MaximumLengthValidator:
    """Reject very long passwords (hashing cost / DoS bound)."""

    def __init__(self, max_length: int = 128) -> None:
        self.max_length = max_length

    def validate(self, password: str, user: Any = None) -> None:
        if len(password) > self.max_length:
            raise ValidationError(
                _("This password is too long (maximum %(max)d characters)."),
                code="password_too_long",
                params={"max": self.max_length},
            )

    def get_help_text(self) -> str:
        return _("Your password can't be longer than %(max)d characters.") % {
            "max": self.max_length
        }


class BreachedPasswordValidator:
    """Optional HIBP Pwned Passwords check with k-anonymity (ADR-037 Q4).

    Disabled unless ``PASSWORD_BREACH_CHECK_ENABLED``. Only the first 5 hex characters of the
    SHA-1 hash leave the server, with ``Add-Padding`` so response sizes reveal nothing.
    When the service is unreachable it fails **open** unless ``PASSWORD_BREACH_CHECK_FAIL_CLOSED``.
    The password itself is never logged.
    """

    timeout_seconds = 2.0

    def validate(self, password: str, user: Any = None) -> None:
        if not settings.PASSWORD_BREACH_CHECK_ENABLED:
            return
        digest = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()
        prefix, suffix = digest[:5], digest[5:]
        try:
            body = self._fetch_range(prefix)
        except (urllib.error.URLError, TimeoutError, OSError):
            logger.warning("password_breach_check_unavailable")
            if settings.PASSWORD_BREACH_CHECK_FAIL_CLOSED:
                raise ValidationError(
                    _("We couldn't check this password right now. Please try again."),
                    code="password_check_unavailable",
                ) from None
            return
        for line in body.splitlines():
            candidate, _sep, count = line.partition(":")
            if candidate.strip() == suffix and count.strip() not in ("", "0"):
                raise ValidationError(
                    _("This password has appeared in a data breach. Choose a different one."),
                    code="password_breached",
                )

    def _fetch_range(self, prefix: str) -> str:
        url = f"{settings.PASSWORD_BREACH_CHECK_URL}{prefix}"
        request = urllib.request.Request(  # noqa: S310 - fixed https URL from settings
            url, headers={"Add-Padding": "true", "User-Agent": "education-erp-password-check"}
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
            return str(response.read().decode("utf-8"))

    def get_help_text(self) -> str:
        return ""
