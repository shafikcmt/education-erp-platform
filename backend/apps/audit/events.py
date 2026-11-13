"""Audit event catalogue with per-event metadata allow-lists (Phase 2 plan §6.8).

``audit.record()`` refuses unknown actions and metadata keys that are not allow-listed for the
action, so request data can never leak into the log by accident. Values must be short scalars.
Secrets (passwords, tokens, MFA secrets/codes, recovery codes, session keys, CSRF tokens) have
no allow-listed key anywhere.
"""

_NONE: frozenset[str] = frozenset()

EVENTS: dict[str, frozenset[str]] = {
    # authentication
    "identity.login.succeeded": frozenset({"mfa", "method"}),
    "identity.login.failed": frozenset({"reason"}),
    "identity.login.locked": frozenset({"reason"}),
    "identity.login.throttled": frozenset({"bucket"}),
    "identity.logout": _NONE,
    # MFA
    "identity.mfa.enrollment_started": frozenset({"device_id"}),
    "identity.mfa.enrollment_cancelled": frozenset({"device_id"}),
    "identity.mfa.manual_key_revealed": frozenset({"device_id", "reason"}),
    "identity.mfa.enrolled": frozenset({"device_id"}),
    "identity.mfa.challenge_failed": frozenset({"reason"}),
    "identity.mfa.disabled": _NONE,
    "identity.mfa.reset": frozenset({"reason"}),
    "identity.mfa.recovery_code_used": frozenset({"remaining", "purpose"}),
    "identity.mfa.locked": frozenset({"reason"}),
    "identity.mfa.recovery_codes_regenerated": frozenset({"count"}),
    # step-up
    "identity.step_up.succeeded": _NONE,
    "identity.step_up.failed": frozenset({"reason"}),
    # passwords / email
    "identity.password.changed": _NONE,
    "identity.password.reset_requested": _NONE,
    "identity.password.reset_completed": _NONE,
    "identity.email.change_requested": _NONE,
    "identity.email.changed": _NONE,
    "identity.token.rejected": frozenset({"purpose", "reason"}),
    # account lifecycle
    "identity.account.created": frozenset({"source"}),
    "identity.account.activated": _NONE,
    "identity.account.activation_resent": _NONE,
    "identity.account.updated": frozenset({"fields"}),
    "identity.account.deactivated": _NONE,
    "identity.account.reactivated": _NONE,
    # sessions
    "identity.session.revoked": frozenset({"reason", "count"}),
    "identity.token.invalidated": frozenset({"reason", "count"}),
    "identity.session.expired_idle": _NONE,
    "identity.session.expired_absolute": _NONE,
    "identity.signin.new_device_notified": _NONE,
    # rbac
    "rbac.role.created": frozenset({"role_code"}),
    "rbac.role.updated": frozenset({"role_code", "fields"}),
    "rbac.role.deleted": frozenset({"role_code"}),
    "rbac.role.permissions_changed": frozenset({"role_code", "added", "removed"}),
    "rbac.platform_role.granted": frozenset({"role_code"}),
    "rbac.platform_role.revoked": frozenset({"role_code"}),
    # owner-only catalogue bootstrap (Phase 3 M1 / O1)
    "rbac.permission_catalog.synced": frozenset({"created", "updated", "deprecated", "declared"}),
    "rbac.system_roles.seeded": frozenset({"roles", "created", "added", "removed"}),
    # audit / authorization
    "audit.ip.revealed": frozenset({"event_id"}),
    "audit.ip.erased": frozenset({"subject_user_id", "count"}),
    "authz.denied": frozenset({"permission", "reason"}),
    # tenant isolation monitoring (Phase 3 M3, P14): platform log, tenant id as metadata only
    "tenancy.isolation.blocked": frozenset({"reason", "tenant_id", "host_kind"}),
    # platform operations (Phase 3, ADR-043): platform_scope start/end
    "platform.operation.started": frozenset({"operation", "reason", "permission"}),
    "platform.operation.completed": frozenset(
        {"operation", "reason", "permission", "tenant_count"}
    ),
}

# Events whose evidence must survive the rollback of a tenant request transaction (Phase 3
# plan §8.3). Inside a tenant context they are always written through the durable connection.
# ``support.*`` and ``invitation.invalid_attempt`` join this set with M5 and M4.
DURABLE_ACTIONS: frozenset[str] = frozenset(
    {
        "authz.denied",
        "identity.login.failed",
        "identity.login.locked",
        "identity.login.throttled",
        "identity.mfa.challenge_failed",
        "identity.mfa.locked",
        "tenancy.isolation.blocked",
    }
)


def allowed_metadata(action: str) -> frozenset[str]:
    try:
        return EVENTS[action]
    except KeyError:
        raise ValueError(f"Unknown audit action: {action!r}") from None
