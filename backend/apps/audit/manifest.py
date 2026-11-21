"""audit module manifest: permissions (Phase 2 plan §5.1, ADR-036)."""

PERMISSIONS = [
    {
        "code": "audit.event.view",
        "description": "View the audit log (platform log on the platform host, the tenant's log "
        "on a tenant host)",
        "requires_mfa": True,
        # P11 / D3: security investigations of a tenant's log only through a support session.
        "support_readable": True,
    },
    {
        "code": "audit.event.view_ip",
        "description": "Reveal decrypted IP addresses (audited)",
        "requires_mfa": True,
        "requires_step_up": True,
        "is_sensitive": True,
    },
]

# Phase 4 M1 (ADR-050): this app's entry in the module catalogue.
MODULE = {
    "code": "audit",
    "name": "Audit log",
    "category": "platform",
    "version": "1.0.0",
    "dependencies": ["core"],
    "sellable": False,
}
