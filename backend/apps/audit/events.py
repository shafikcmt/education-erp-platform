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
    # module catalogue bootstrap (Phase 4 M1, ADR-050)
    "module_registry.catalog.synced": frozenset({"created", "updated", "deprecated", "declared"}),
    # billing and entitlements (Phase 4 M2): platform log; P18 changes also in the tenant log
    "billing.plan.created": frozenset({"plan_code"}),
    "billing.plan.updated": frozenset({"plan_code", "fields"}),
    "billing.plan.modules_changed": frozenset({"plan_code", "added", "removed"}),
    "billing.addon.created": frozenset({"addon_code", "module_code"}),
    "billing.price.added": frozenset({"target", "currency", "interval", "amount"}),
    "billing.price.deactivated": frozenset({"target", "currency", "interval"}),
    "billing.subscription.plan_changed": frozenset({"tenant_id", "old", "new", "reason"}),
    "billing.subscription.trial_set": frozenset({"tenant_id", "days", "reason"}),
    "billing.subscription.addon_added": frozenset({"tenant_id", "addon_code", "reason"}),
    "billing.subscription.addon_removed": frozenset({"tenant_id", "addon_code", "reason"}),
    "module_registry.override.set": frozenset({"tenant_id", "module_code", "kind", "reason"}),
    "module_registry.override.ended": frozenset({"tenant_id", "module_code", "reason"}),
    "module_registry.flag.changed": frozenset({"flag_key", "default_enabled"}),
    # tenant roles, assignments, members and invitations (Phase 3 M4): tenant log
    "rbac.assignment.granted": frozenset({"role_code", "scope_type"}),
    "rbac.assignment.revoked": frozenset({"role_code", "scope_type"}),
    "rbac.tenant_roles.synced": frozenset({"tenants", "changed", "failed"}),
    "tenancy.member.suspended": _NONE,
    "tenancy.member.reactivated": _NONE,
    "tenancy.member.removed": _NONE,
    "tenancy.invitation.created": frozenset({"role_code", "scope_type"}),
    "tenancy.invitation.resent": _NONE,
    "tenancy.invitation.revoked": _NONE,
    "tenancy.invitation.accepted": frozenset({"role_code", "scope_type"}),
    "tenancy.invitation.invalid_attempt": frozenset({"reason"}),
    # support sessions (Phase 3 M5, ADR-045): tenant log
    "support.session.requested": frozenset({"minutes", "auto_approved"}),
    "support.session.approved": frozenset({"minutes"}),
    "support.session.rejected": _NONE,
    "support.session.started": _NONE,
    "support.session.revoked": frozenset({"reason"}),
    "support.session.ended": _NONE,
    "support.session.expired": _NONE,
    "support.request": frozenset({"method", "path"}),
    "support.access_denied": frozenset({"reason"}),
    "support.write_rejected": frozenset({"method"}),
    "tenancy.support_approval.changed": frozenset({"old", "new", "reason"}),
    # tenant registry and structure (Phase 3 M8). Registry events are written to both logs.
    "tenancy.tenant.provisioned": frozenset({"slug", "tenant_id"}),
    "tenancy.tenant.provisioning_failed": frozenset({"slug", "tenant_id", "error"}),
    "tenancy.tenant.updated": frozenset({"fields", "tenant_id"}),
    "tenancy.tenant.suspended": frozenset({"reason", "tenant_id", "revoked_support_count"}),
    "tenancy.tenant.reactivated": frozenset({"reason", "tenant_id"}),
    "tenancy.tenant.limits_overridden": frozenset(
        {"reason", "tenant_id", "max_institutions", "max_campuses"}
    ),
    "tenancy.tenant.owner_invited": frozenset({"tenant_id"}),
    "tenancy.profile.updated": frozenset({"fields"}),
    "tenancy.institution.created": frozenset({"object_code"}),
    "tenancy.institution.updated": frozenset({"fields"}),
    "tenancy.institution.archived": _NONE,
    "tenancy.campus.created": frozenset({"object_code"}),
    "tenancy.campus.updated": frozenset({"fields"}),
    "tenancy.campus.archived": _NONE,
    # audit / authorization
    "audit.ip.revealed": frozenset({"event_id"}),
    "audit.ip.erased": frozenset({"subject_user_id", "count"}),
    "authz.denied": frozenset({"permission", "module", "reason"}),
    # Phase 5 M1: configuration versions (tenant log; key names only, never values)
    "customization.presets.synced": frozenset({"declared", "created", "deprecated"}),
    "customization.config.draft_saved": frozenset(
        {"scope", "number", "added", "removed", "changed"}
    ),
    "customization.config.draft_discarded": frozenset({"scope", "number"}),
    "customization.config.published": frozenset({"scope", "number", "added", "removed", "changed"}),
    "customization.config.rolled_back": frozenset(
        {"scope", "number", "source", "added", "removed", "changed"}
    ),
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
DURABLE_ACTIONS: frozenset[str] = frozenset(
    {
        "authz.denied",
        "identity.login.failed",
        "identity.login.locked",
        "identity.login.throttled",
        "identity.mfa.challenge_failed",
        "identity.mfa.locked",
        "support.access_denied",
        "support.write_rejected",
        "tenancy.invitation.invalid_attempt",
        "tenancy.isolation.blocked",
    }
)


def allowed_metadata(action: str) -> frozenset[str]:
    try:
        return EVENTS[action]
    except KeyError:
        raise ValueError(f"Unknown audit action: {action!r}") from None
