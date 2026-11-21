"""identity module manifest: permissions (Phase 2 plan §5.1).

Self-service codes (``*_own``, ``identity.mfa.manage_own``) are granted to every active user by
``SelfServiceSource``. Step-up for own-MFA operations is enforced per endpoint (disable,
recovery regeneration, manual-key reveal), because starting a QR enrollment must not need it.
"""

PERMISSIONS = [
    {"code": "identity.account.view_own", "description": "View own profile"},
    {"code": "identity.account.update_own", "description": "Update own profile"},
    {"code": "identity.session.view_own", "description": "View own sessions"},
    {"code": "identity.session.revoke_own", "description": "Revoke own sessions"},
    {"code": "identity.mfa.manage_own", "description": "Enroll in or remove own MFA"},
    {"code": "identity.user.view", "description": "View platform users", "requires_mfa": True},
    {"code": "identity.user.create", "description": "Create platform users", "requires_mfa": True},
    {"code": "identity.user.update", "description": "Update platform users", "requires_mfa": True},
    {
        "code": "identity.user.deactivate",
        "description": "Deactivate or reactivate users",
        "requires_mfa": True,
        "requires_step_up": True,
    },
    {
        "code": "identity.user.view_sensitive",
        "description": "View MFA state and session details of other users",
        "requires_mfa": True,
        "is_sensitive": True,
    },
    {
        "code": "identity.session.revoke_any",
        "description": "Revoke another user's sessions",
        "requires_mfa": True,
        "requires_step_up": True,
    },
    {
        "code": "identity.mfa.reset",
        "description": "Reset another user's MFA (reason required)",
        "requires_mfa": True,
        "requires_step_up": True,
    },
]

# Phase 4 M1 (ADR-050): this app's entry in the module catalogue.
MODULE = {
    "code": "identity",
    "name": "Identity",
    "category": "platform",
    "version": "1.0.0",
    "dependencies": ["core"],
    "sellable": False,
}
