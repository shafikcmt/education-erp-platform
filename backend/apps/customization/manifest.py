"""customization manifest (Phase 5; ADR-057).

Studio permissions are tenant codes held in a scope: an owner configures the whole
organisation, an institution admin their institution. Publishing changes what every member
sees, so it needs MFA and a fresh step-up.
"""

MODULE = {
    "code": "customization",
    "name": "Customization Studio",
    "category": "platform",
    "version": "1.0.0",
    "dependencies": ["module_registry"],
    "sellable": False,
}

PERMISSIONS = [
    {"code": "customization.config.view", "description": "View configuration and its history"},
    {
        "code": "customization.config.edit",
        "description": "Edit the configuration draft",
        "requires_mfa": True,
    },
    {
        "code": "customization.config.publish",
        "description": "Publish or roll back configuration",
        "requires_mfa": True,
        "requires_step_up": True,
    },
]

# Declared configuration keys (ADR-057). Every key belongs to the module whose code prefixes
# it; values are validated against ``schema``; ``scopes`` are where a value may be set.
SETTINGS = {
    "customization.terminology": {
        "description": "Terminology overrides per locale, e.g. {'en': {'unit.section': 'Jamaat'}}",
        "schema": {
            "type": "object",
            "propertyNames": {"pattern": "^[a-z]{2}(-[A-Z]{2})?$"},
            "additionalProperties": {
                "type": "object",
                "propertyNames": {"pattern": "^[a-z][a-z0-9_.]{1,79}$"},
                "additionalProperties": {"type": "string", "minLength": 1, "maxLength": 80},
                "maxProperties": 300,
            },
            "maxProperties": 10,
        },
        "default": {},
        "scopes": ["tenant", "institution", "campus"],
        "merge": "deep",
    },
    # Phase 5 M2: preset-driven keys (ADR-058). Code branches on capability flags, centrally,
    # never on the institution type (CLAUDE.md §4).
    "customization.capabilities": {
        "description": "Capability flags, e.g. {'academics.credit_based': true}",
        "schema": {
            "type": "object",
            "propertyNames": {"pattern": "^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]{1,63}$"},
            "additionalProperties": {"type": "boolean"},
            "maxProperties": 100,
        },
        "default": {},
        "scopes": ["institution"],
        "merge": "deep",
    },
    "customization.structure_levels": {
        "description": "Academic structure levels, broadest first, with their labels",
        "schema": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "required": ["key"],
                "additionalProperties": False,
                "properties": {"key": {"type": "string", "pattern": "^[a-z][a-z0-9_]{1,39}$"}},
            },
        },
        "default": [],
        "scopes": ["institution"],
    },
    "customization.role_labels": {
        "description": "Role template labels per locale, e.g. {'en': {'teacher': 'Ustad'}}",
        "schema": {
            "type": "object",
            "propertyNames": {"pattern": "^[a-z]{2}(-[A-Z]{2})?$"},
            "additionalProperties": {
                "type": "object",
                "propertyNames": {"pattern": "^[a-z][a-z0-9_]{1,63}$"},
                "additionalProperties": {"type": "string", "minLength": 1, "maxLength": 80},
            },
        },
        "default": {},
        "scopes": ["tenant", "institution"],
        "merge": "deep",
    },
}
