"""Pure domain rules for tenants (Phase 3 M2; plan §4.1, §4.3, §10.4, Q12).

No database access here: the same rules are used by the models, the services of later
milestones and (as literal SQL) by the database constraints and the ``tenancy_tenant`` guard
trigger, so the application and PostgreSQL agree.
"""

from __future__ import annotations

import re
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError

# --------------------------------------------------------------------------- slugs (§10.4)
SLUG_PATTERN = r"^[a-z][a-z0-9-]{1,30}[a-z0-9]$"
_SLUG_RE = re.compile(SLUG_PATTERN)

# Hosts the platform needs for itself, or that invite confusion/phishing. Never assignable.
RESERVED_SLUGS: frozenset[str] = frozenset(
    {
        "admin",
        "api",
        "app",
        "assets",
        "auth",
        "billing",
        "blog",
        "cdn",
        "dashboard",
        "dev",
        "docs",
        "ftp",
        "help",
        "imap",
        "login",
        "mail",
        "media",
        "ns1",
        "ns2",
        "platform",
        "pop",
        "portal",
        "root",
        "security",
        "smtp",
        "sso",
        "staging",
        "static",
        "status",
        "support",
        "system",
        "test",
        "www",
    }
)


class InvalidSlug(ValidationError):  # noqa: N818 - Django ValidationError family
    pass


def validate_slug(slug: str) -> str:
    """Return ``slug`` if it is a valid, non-reserved tenant slug; raise ``InvalidSlug``."""
    if not isinstance(slug, str) or not _SLUG_RE.match(slug):
        raise InvalidSlug(
            "Use 3-32 characters: lower-case letters, digits and hyphens; start with a letter "
            "and end with a letter or digit.",
            code="invalid_slug",
        )
    if "--" in slug:
        raise InvalidSlug("Consecutive hyphens are not allowed.", code="invalid_slug")
    if slug in RESERVED_SLUGS:
        raise InvalidSlug("This name is reserved.", code="reserved_slug")
    return slug


# --------------------------------------------------------------------------- lifecycle (§4.3)
class TenantStatus:
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    OFFBOARDING = "offboarding"
    DELETED = "deleted"

    CHOICES = (
        (PROVISIONING, "Provisioning"),
        (ACTIVE, "Active"),
        (SUSPENDED, "Suspended"),
        (OFFBOARDING, "Offboarding"),
        (DELETED, "Deleted"),
    )


# Allowed status changes. ``deleted`` is terminal: the slug stays tombstoned forever.
TRANSITIONS: dict[str, frozenset[str]] = {
    TenantStatus.PROVISIONING: frozenset({TenantStatus.ACTIVE, TenantStatus.DELETED}),
    TenantStatus.ACTIVE: frozenset({TenantStatus.SUSPENDED, TenantStatus.OFFBOARDING}),
    TenantStatus.SUSPENDED: frozenset({TenantStatus.ACTIVE, TenantStatus.OFFBOARDING}),
    TenantStatus.OFFBOARDING: frozenset({TenantStatus.ACTIVE, TenantStatus.DELETED}),
    TenantStatus.DELETED: frozenset(),
}

# Statuses whose hosts resolve (F1); provisioning/deleted are indistinguishable from unknown.
RESOLVABLE_STATUSES: frozenset[str] = frozenset(
    {TenantStatus.ACTIVE, TenantStatus.SUSPENDED, TenantStatus.OFFBOARDING}
)


class InvalidStatusTransition(ValidationError):  # noqa: N818 - Django ValidationError family
    pass


def check_transition(old: str, new: str) -> None:
    if new not in TRANSITIONS.get(old, frozenset()):
        raise InvalidStatusTransition(
            f"A tenant can't move from {old!r} to {new!r}.", code="invalid_status_transition"
        )


# --------------------------------------------------------------------------- limits (Q12)
LIMIT_KEYS = ("max_institutions", "max_campuses")


def default_limits() -> dict[str, Any]:
    """Defaults stored on each new tenant (settings ``TENANT_DEFAULT_LIMITS``: 1 / 3)."""
    configured = dict(getattr(settings, "TENANT_DEFAULT_LIMITS", {}))
    return {key: int(configured[key]) for key in LIMIT_KEYS}


def default_tenant_settings() -> dict[str, Any]:
    # Q4 / D5: tenant approval of support sessions is required by default.
    return {"support_access_requires_approval": True}


# --------------------------------------------------------------------------- domains
# Lower-case LDH host name with at least two labels (length <= 253 is a column limit). IP
# literals are rejected separately (all-numeric names).
DOMAIN_PATTERN = r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$"
NUMERIC_HOST_PATTERN = r"^[0-9.]+$"
_DOMAIN_RE = re.compile(DOMAIN_PATTERN)
_NUMERIC_RE = re.compile(NUMERIC_HOST_PATTERN)


def is_valid_domain(host: object) -> bool:
    return (
        isinstance(host, str)
        and len(host) <= 253
        and bool(_DOMAIN_RE.match(host))
        and not _NUMERIC_RE.match(host)
    )
