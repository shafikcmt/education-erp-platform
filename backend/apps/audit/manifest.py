"""audit module manifest: permissions (Phase 2 plan §5.1, ADR-036)."""

PERMISSIONS = [
    {
        "code": "audit.event.view",
        "description": "View the platform audit log",
        "requires_mfa": True,
    },
    {
        "code": "audit.event.view_ip",
        "description": "Reveal decrypted IP addresses (audited)",
        "requires_mfa": True,
        "requires_step_up": True,
        "is_sensitive": True,
    },
]
