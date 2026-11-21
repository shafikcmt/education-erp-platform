"""module_registry manifest (Phase 4; ADR-050)."""

MODULE = {
    "code": "module_registry",
    "name": "Module registry",
    "category": "platform",
    "version": "1.0.0",
    "dependencies": ["tenancy"],
    "sellable": False,
}

PERMISSIONS = [
    {
        "code": "module_registry.module.view",
        "description": "View the module catalogue",
        "requires_mfa": True,
    },
    {
        "code": "module_registry.flag.manage",
        "description": "Create and change feature flags",
        "requires_mfa": True,
    },
]
