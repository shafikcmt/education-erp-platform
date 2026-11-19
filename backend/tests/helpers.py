"""Shared Phase 2 test helpers: users with roles/MFA, a CSRF-aware API client, login flows.

Logins always go through the real API (so ``SessionRecord`` and session state exist), never
``client.force_login``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import pyotp
from django.test import Client
from django.utils import timezone

from apps.core import crypto
from apps.identity.models import MFADevice, MFAKind, User
from apps.rbac.models import PlatformRoleAssignment, Role, RoleKind

PASSWORD = "Correct-Horse-Battery-9"


def link_token(message: Any, page: str = "") -> str:
    """Raw token from an email link (``/<page>#token=...``)."""
    found = re.search(rf"{page}#token=([A-Za-z0-9_\-]+)", str(message.body))
    assert found, message.body
    return found.group(1)


@dataclass
class Person:
    user: User
    password: str = PASSWORD
    totp_secret: str | None = None

    def code(self, offset_steps: int = 0) -> str:
        assert self.totp_secret
        totp = pyotp.TOTP(self.totp_secret)
        return totp.generate_otp(totp.timecode(timezone.now()) + offset_steps)


def make_user(
    email: str = "person@example.com",
    *,
    password: str | None = PASSWORD,
    activated: bool = True,
    active: bool = True,
    roles: tuple[str, ...] = (),
    mfa: bool = False,
    locale: str = "en",
) -> Person:
    user = User.objects.create_user(email, password, locale=locale)
    user.is_active = active
    if activated:
        user.activated_at = timezone.now()
        user.email_verified_at = timezone.now()
    user.save()
    for code in roles:
        role = Role.objects.get(tenant_id__isnull=True, code=code, kind=RoleKind.PLATFORM)
        PlatformRoleAssignment.objects.create(user=user, role=role, granted_at=timezone.now())
    secret = None
    if mfa:
        secret = pyotp.random_base32()
        device = MFADevice(user=user, kind=MFAKind.TOTP, confirmed_at=timezone.now())
        device.secret_encrypted = crypto.encrypt_str(
            secret, purpose=f"identity.mfadevice.secret:{device.pk}"
        )
        device.save()
    return Person(user=user, password=password or "", totp_secret=secret)


def enroll_mfa(user: User) -> Person:
    """Give an existing account a confirmed TOTP device (Phase 3: tenant administrators)."""
    secret = pyotp.random_base32()
    device = MFADevice(user=user, kind=MFAKind.TOTP, confirmed_at=timezone.now())
    device.secret_encrypted = crypto.encrypt_str(
        secret, purpose=f"identity.mfadevice.secret:{device.pk}"
    )
    device.save()
    return Person(user=user, totp_secret=secret)


class Api:
    """JSON client that enforces CSRF like a browser: fetches the cookie, sends the header."""

    def __init__(
        self, *, remote_addr: str = "198.51.100.7", user_agent: str = "", host: str = ""
    ) -> None:
        # ``host`` (Phase 3): a tenant host such as ``acme.tenants.test``; default ``testserver``.
        extra: dict[str, Any] = {"HTTP_HOST": host} if host else {}
        self.client = Client(
            enforce_csrf_checks=True,
            **extra,
            REMOTE_ADDR=remote_addr,
            HTTP_USER_AGENT=user_agent
            or "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/140.0",
        )

    def _csrf(self) -> str:
        if "csrftoken" not in self.client.cookies:
            self.client.get("/api/v1/auth/csrf/")
        return self.client.cookies["csrftoken"].value

    def get(self, path: str, **params: Any) -> Any:
        return self.client.get(path, params)

    def send(self, method: str, path: str, data: Any = None, *, csrf: bool = True) -> Any:
        headers = {"HTTP_X_CSRFTOKEN": self._csrf()} if csrf else {}
        body = json.dumps(data) if data is not None else ""
        return getattr(self.client, method)(path, body, content_type="application/json", **headers)

    def post(self, path: str, data: Any = None, **kw: Any) -> Any:
        return self.send("post", path, data, **kw)

    def patch(self, path: str, data: Any = None, **kw: Any) -> Any:
        return self.send("patch", path, data, **kw)

    def delete(self, path: str, data: Any = None, **kw: Any) -> Any:
        return self.send("delete", path, data, **kw)

    # ----------------------------------------------------------- flows
    def login(self, person: Person, *, expect: str | None = None) -> Any:
        response = self.post(
            "/api/v1/auth/login/", {"email": person.user.email, "password": person.password}
        )
        assert response.status_code == 200, response.content
        status = response.json()["status"]
        if status == "mfa_required":
            response = self.post("/api/v1/auth/mfa/verify/", {"code": person.code()})
            assert response.status_code == 200, response.content
            status = response.json()["status"]
        if expect is not None:
            assert status == expect
        return status

    def step_up(self, person: Person, *, offset_steps: int = 1) -> Any:
        data: dict[str, str] = {"password": person.password}
        if person.totp_secret:
            # A step not yet used at login (replay protection rejects reused steps).
            data["code"] = person.code(offset_steps)
        response = self.post("/api/v1/auth/step-up/", data)
        assert response.status_code == 200, response.content
        return response
