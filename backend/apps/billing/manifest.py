"""billing manifest (Phase 4; ADR-051, ADR-054).

Platform codes (P17/P18): plans, add-ons and prices are managed by ``platform_billing`` and the
Super Admin; price and subscription changes need a fresh step-up. Tenant code
``billing.subscription.view`` lets owners see their own subscription (Phase 4 M5 page).
"""

MODULE = {
    "code": "billing",
    "name": "Billing",
    "category": "platform",
    "version": "1.0.0",
    "dependencies": ["module_registry"],
    "sellable": False,
}

PERMISSIONS = [
    {"code": "billing.plan.view", "description": "View plans and add-ons", "requires_mfa": True},
    {
        "code": "billing.plan.manage",
        "description": "Create and change plans and add-ons",
        "requires_mfa": True,
    },
    {
        "code": "billing.price.manage",
        "description": "Add or deactivate prices",
        "requires_mfa": True,
        "requires_step_up": True,
    },
    {
        "code": "billing.subscription.view_any",
        "description": "View any tenant's subscription",
        "requires_mfa": True,
    },
    {
        "code": "billing.subscription.manage",
        "description": "Change a tenant's plan, add-ons, trial and module overrides",
        "requires_mfa": True,
        "requires_step_up": True,
    },
    {
        "code": "billing.subscription.view",
        "description": "View the organisation's subscription",
        "support_readable": True,
    },
]
