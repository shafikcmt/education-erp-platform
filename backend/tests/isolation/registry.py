"""Explicit isolation registry checked by ``test_rls_coverage.py`` (plan §5.2, §5.3; ADR-046).

Every table in the ``public`` schema must fall into exactly one class:

* a **standard tenant table** (has ``tenant_id NOT NULL``; ENABLE + FORCE RLS; the standard
  per-command policies);
* a **dual-scope** table (``DUAL_SCOPE_TABLES``);
* a **self-scoped registry** table (``SELF_SCOPED_TABLES``; ``tenancy_tenant`` in M2);
* a table whose RLS is **scheduled for a later milestone** (``PENDING_RLS``): it must have no
  RLS at all until then, never a half-configured state;
* a **registry table without RLS** (``REGISTRY_ALLOWLIST``): each entry needs a justification
  and the access-control tests that cover it (``path::test_name``, verified to exist).

Adding a table without registering it, or registering it without justification and tests,
fails CI.
"""

from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------- policy classes
# The probes are created by the real migration operations; their policies are the reference
# shape for each class.
REFERENCE_PROBES: dict[str, str] = {
    "standard": "isolation_probe_record",
    "dual": "isolation_probe_dual",
    "dual_private": "isolation_probe_dual_private",
}

DUAL_SCOPE_TABLES: dict[str, str] = {
    "isolation_probe_dual": "dual",
    "isolation_probe_dual_private": "dual_private",
}

# Registry tables keyed by their own id (plan §5.1). tenancy_tenant: the platform sees every
# row, a tenant context only its own (M2, ``EnableSelfScopedRLS``).
SELF_SCOPED_TABLES: dict[str, str] = {"tenancy_tenant": "id"}


@dataclass(frozen=True)
class Pending:
    kind: str
    milestone: str
    note: str


# Phase 2 tables whose policies are part of a later Phase 3 milestone (plan §20). Until then
# they must have NO row security at all; the milestone moves them to DUAL_SCOPE_TABLES.
PENDING_RLS: dict[str, Pending] = {
    "rbac_role": Pending("dual", "M6", "Platform templates + tenant role copies (plan §5.1)."),
    "rbac_rolepermission": Pending("dual", "M6", "Follows rbac_role (tenant-sync trigger)."),
    "audit_auditevent": Pending("dual_private", "M6", "Platform and tenant audit events."),
    "audit_auditeventip": Pending(
        "dual_private", "M6", "Gains a trigger-filled tenant_id in audit.0004 (plan §19.1)."
    ),
}


# --------------------------------------------------------------------------- registry tables
@dataclass(frozen=True)
class AllowEntry:
    justification: str
    tests: tuple[str, ...]


_PLATFORM_AUTHZ = (
    "tests/test_platform_api_authorization.py::test_anonymous_is_401_everywhere",
    "tests/test_platform_api_authorization.py::test_ordinary_user_is_403_everywhere",
    "tests/test_url_authorization_audit.py::test_every_api_view_is_authorized_or_reviewed",
)

REGISTRY_ALLOWLIST: dict[str, AllowEntry] = {
    "identity_user": AllowEntry(
        "One global account per person (CLAUDE.md §9, ADR-032); needed before any tenant "
        "context exists (sign-in). Platform user administration requires platform permissions.",
        (
            *_PLATFORM_AUTHZ,
            "apps/identity/tests/test_account_flows.py::test_password_reset_is_enumeration_safe_and_revokes_all_sessions",
        ),
    ),
    "identity_accounttoken": AllowEntry(
        "Per-user email-link tokens (hashed, ADR-034); independent of tenants.",
        (
            "tests/test_security_review_fixes.py::test_m2_password_reset_invalidates_tokens_of_other_purposes",
            "apps/identity/tests/test_account_flows.py::test_tokens_have_the_documented_lifetimes",
        ),
    ),
    "identity_mfadevice": AllowEntry(
        "Per-user MFA devices (encrypted secrets, ADR-031); own account or platform MFA reset.",
        (
            "apps/identity/tests/test_mfa.py::test_admin_mfa_reset_requires_reason_step_up_and_revokes_sessions",
            "tests/test_security_review_fixes.py::test_h2_actor_must_hold_every_permission_of_the_target",
        ),
    ),
    "identity_recoverycode": AllowEntry(
        "Per-user MFA recovery codes (hashed); own account only.",
        ("apps/identity/tests/test_mfa.py::test_recovery_codes_are_hashed_and_single_use",),
    ),
    "identity_sessionrecord": AllowEntry(
        "Per-user session index (hashed keys, encrypted IPs); own sessions or platform revoke.",
        (
            "apps/identity/tests/test_sessions.py::test_cannot_revoke_someone_elses_session",
            "apps/identity/tests/test_sessions.py::test_admin_revoke_any_needs_permission_and_step_up",
        ),
    ),
    "identity_seendevice": AllowEntry(
        "Per-user new-sign-in fingerprints (HMAC, 90-day retention, ADR-036/040).",
        (
            "tests/test_security_review_fixes.py::test_m4_device_fingerprints_expire_after_90_days_and_are_erased",
        ),
    ),
    "rbac_permission": AllowEntry(
        "Global, code-defined permission catalogue shared by every tenant; no tenant data. "
        "SELECT only for the runtime role (O1, rbac.0003); written only by the owner-run "
        "bootstrap (sync_permissions/seed_roles); no API creates or changes permissions.",
        (
            "apps/rbac/tests/test_api.py::test_permission_catalog_lists_flags",
            "tests/test_permission_catalog.py::test_runtime_role_can_only_read_the_permission_catalog",
            "tests/test_permission_catalog.py::test_seeding_functions_and_commands_refuse_the_runtime_role",
            "tests/test_permission_catalog.py::test_owner_bootstrap_is_repeatable_idempotent_and_runtime_role_is_refused",
        ),
    ),
    "rbac_platformroleassignment": AllowEntry(
        "Platform staff roles; platform permissions never apply to tenant targets (ADR-033).",
        (
            "apps/rbac/tests/test_engine.py::test_super_admin_has_no_implicit_tenant_access",
            "apps/rbac/tests/test_api.py::test_non_super_admin_cannot_grant_super_admin",
        ),
    ),
    "django_session": AllowEntry(
        "Framework session store keyed by a random session key; host-only cookies (ADR-011).",
        ("apps/identity/tests/test_sessions.py::test_session_key_is_never_stored_in_plaintext",),
    ),
    "django_migrations": AllowEntry(
        "Framework migration history; SELECT only for the runtime role (Phase 2).",
        (
            "apps/core/tests/test_db_grants.py::test_runtime_role_can_read_but_not_write_migration_history",
        ),
    ),
    "django_content_type": AllowEntry(
        "Framework metadata written only by migrate; SELECT only for the runtime role (M1).",
        (
            "apps/core/tests/test_db_grants.py::test_framework_tables_are_read_only_for_runtime_role",
        ),
    ),
    "auth_permission": AllowEntry(
        "Django permissions, unused for authorization (ADR-033); SELECT only (M1).",
        (
            "apps/core/tests/test_db_grants.py::test_framework_tables_are_read_only_for_runtime_role",
        ),
    ),
    "auth_group": AllowEntry(
        "Django groups, unused for authorization (ADR-033); SELECT only (M1).",
        (
            "apps/core/tests/test_db_grants.py::test_framework_tables_are_read_only_for_runtime_role",
        ),
    ),
    "auth_group_permissions": AllowEntry(
        "Django group permissions, unused (ADR-033); SELECT only (M1).",
        (
            "apps/core/tests/test_db_grants.py::test_framework_tables_are_read_only_for_runtime_role",
        ),
    ),
    "identity_user_groups": AllowEntry(
        "Django user-group links, unused (ADR-033); SELECT and DELETE only (M1).",
        ("apps/core/tests/test_db_grants.py::test_user_link_tables_allow_only_select_and_delete",),
    ),
    "identity_user_user_permissions": AllowEntry(
        "Django user-permission links, unused (ADR-033); SELECT and DELETE only (M1).",
        ("apps/core/tests/test_db_grants.py::test_user_link_tables_allow_only_select_and_delete",),
    ),
}

# Unique constraints on standard tenant tables must start with tenant_id (plan §4.4 (5)).
# Justified global exceptions (unique-constraint checks bypass RLS, so each is an existence
# oracle only for values that are public or unguessable):
# * a host name is public in DNS anyway, and must be globally unique to resolve;
# * an invitation token hash is the SHA-256 of 256 random bits.
UNIQUE_EXCEPTIONS: frozenset[tuple[str, tuple[str, ...]]] = frozenset(
    {
        ("tenancy_tenantdomain", ("domain",)),
        ("tenancy_invitation", ("token_hash",)),
    }
)

# Reviewed SECURITY DEFINER functions (plan §7: F1-F3, threat-modelled; tests in
# apps/tenancy/tests/test_definer_functions.py). Anything else fails.
DEFINER_FUNCTIONS: frozenset[str] = frozenset(
    {"tenancy_resolve_host", "tenancy_memberships_of", "tenancy_support_sessions_of"}
)

# Reviewed owner-only SELECT policies backing the definer functions (plan §7). They apply only
# to the owner role (never to erp_app) and must be SELECT only.
OWNER_POLICIES: frozenset[tuple[str, str]] = frozenset(
    {
        ("tenancy_tenantdomain", "definer_resolve_host"),
        ("tenancy_membership", "definer_memberships_of"),
        ("tenancy_supportsession", "definer_support_sessions_of"),
    }
)
