"""Security emails (en/bn) sent through Celery (plan §6.4, §6.5, §6.11; platform tasks).

Email links carry a raw token, so the task payload is **sealed** with the ADR-031 key ring
before it reaches the broker; the worker opens it, renders the templates and sends. Neither the
payload nor the rendered body is ever logged. Templates live in
``identity/templates/identity/email/<name>.<locale>.{subject,body}.txt``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone, translation

from apps.core import crypto

if TYPE_CHECKING:
    from apps.identity.models import User

_PURPOSE = "identity.email.task"
TEMPLATES = frozenset(
    {
        "activation",
        "password_reset",
        "password_reset_done",
        "password_changed",
        "email_change_verify",
        "email_change_notice",
        "email_changed",
        "lockout_notice",
        "new_signin",
        "mfa_reset",
        "mfa_disabled",
    }
)


def link(locale: str, page: str, token: str | None = None) -> str:
    """Frontend link; tokens go in the URL fragment (never sent to servers or in Referer)."""
    base = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/{locale}/{page}"
    return f"{base}#token={token}" if token else base


def _locale(user: User | None, fallback: str = "en") -> str:
    supported = {code for code, _ in settings.LANGUAGES}
    value = getattr(user, "locale", "") or fallback
    return value if value in supported else settings.LANGUAGE_CODE


def send_security_email(
    template: str, *, to: str, user: User | None, context: dict[str, Any] | None = None
) -> None:
    if template not in TEMPLATES:
        raise ValueError(f"Unknown email template {template!r}")
    locale = _locale(user)
    payload = {
        "template": template,
        "to": to,
        "locale": locale,
        "context": {
            "display_name": getattr(user, "display_name", "") or "",
            "security_url": link(locale, "account/security"),
            "forgot_url": link(locale, "forgot-password"),
            "sent_at": timezone.now().strftime("%Y-%m-%d %H:%M UTC"),
            **(context or {}),
        },
    }
    sealed = crypto.encrypt(json.dumps(payload).encode(), purpose=_PURPOSE)
    from apps.identity.tasks import deliver_security_email

    deliver_security_email.delay(sealed.hex())


def deliver(sealed_hex: str) -> None:
    payload = json.loads(crypto.decrypt(bytes.fromhex(sealed_hex), purpose=_PURPOSE))
    name, locale = payload["template"], payload["locale"]
    with translation.override(locale):
        base = f"identity/email/{name}.{locale}"
        subject = render_to_string(f"{base}.subject.txt", payload["context"]).strip()
        body = render_to_string(f"{base}.body.txt", payload["context"])
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [payload["to"]])
