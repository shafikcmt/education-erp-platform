"""rbac module manifest: permissions (Phase 2 plan §5.1)."""

PERMISSIONS = [
    {
        "code": "rbac.permission.view",
        "description": "View the permission catalog",
        "requires_mfa": True,
    },
    {"code": "rbac.role.view", "description": "View roles", "requires_mfa": True},
    {
        "code": "rbac.role.create",
        "description": "Create roles",
        "requires_mfa": True,
        "requires_step_up": True,
    },
    {
        "code": "rbac.role.update",
        "description": "Update roles",
        "requires_mfa": True,
        "requires_step_up": True,
    },
    {
        "code": "rbac.role.delete",
        "description": "Delete roles",
        "requires_mfa": True,
        "requires_step_up": True,
    },
    {
        "code": "rbac.platform_role.assign",
        "description": "Grant or revoke platform roles",
        "requires_mfa": True,
        "requires_step_up": True,
    },
    # Phase 3 M4: tenant-scope role management (plan §12.3).
    {
        "code": "rbac.role.clone",
        "description": "Clone a role into an editable tenant role",
        "requires_mfa": True,
        "requires_step_up": True,
    },
    {
        "code": "rbac.assignment.view",
        "description": "View role assignments",
        "requires_mfa": True,
    },
    {
        "code": "rbac.assignment.manage",
        "description": "Grant or revoke tenant role assignments",
        "requires_mfa": True,
        "requires_step_up": True,
    },
]
