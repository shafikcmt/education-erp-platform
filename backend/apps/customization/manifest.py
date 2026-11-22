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
    # Phase 5 M3: rules and custom fields (drafted with ``manage``; going live needs
    # ``customization.config.publish``).
    {"code": "customization.rule.view", "description": "View rules"},
    {
        "code": "customization.rule.manage",
        "description": "Create and test rules",
        "requires_mfa": True,
    },
    {"code": "customization.field.view", "description": "View custom field definitions"},
    {
        "code": "customization.field.manage",
        "description": "Define and deprecate custom fields",
        "requires_mfa": True,
    },
    # Phase 5 M4: forms and workflow definitions.
    {"code": "customization.form.view", "description": "View form definitions"},
    {"code": "customization.form.manage", "description": "Design forms", "requires_mfa": True},
    {"code": "customization.workflow.view", "description": "View workflow definitions"},
    {
        "code": "customization.workflow.manage",
        "description": "Design approval workflows",
        "requires_mfa": True,
    },
    # Phase 5 M5: templates and numbering sequences.
    {"code": "customization.template.view", "description": "View templates"},
    {
        "code": "customization.template.manage",
        "description": "Design templates",
        "requires_mfa": True,
    },
    {"code": "customization.numbering.view", "description": "View numbering sequences"},
    {
        "code": "customization.numbering.manage",
        "description": "Define numbering sequences",
        "requires_mfa": True,
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

# Rule namespaces (ADR-055): where rules run, which variables they may read, what they return.
# Modules add theirs (e.g. ``fees.late_fine`` in Phase 10).
RULE_NAMESPACES = {
    "customization.form_visibility": {
        "description": "Show a form section or field when the rule is true",
        "variables": ["field.*", "today"],
        "result": "boolean",
    },
    "customization.workflow_guard": {
        "description": "Allow a workflow transition when the rule is true",
        "variables": ["subject.*", "today"],
        "result": "boolean",
    },
}

# Template kinds (ADR-056): output format, the variables a template may use, a sample context
# for previews and an output limit. Modules add theirs (receipts, report cards, ID cards …).
TEMPLATE_KINDS = {
    "customization.email": {
        "format": "text",
        "subject": True,
        "max_output": 20_000,
        "variables": {
            "organisation": "Organisation name",
            "recipient": "Recipient name",
            "link": "A link",
        },
        "sample": {"organisation": "Example Academy", "recipient": "A. Rahman", "link": "/x"},
    },
    "customization.sms": {
        "format": "text",
        "subject": False,
        "max_output": 480,
        "variables": {"organisation": "Organisation name", "recipient": "Recipient name"},
        "sample": {"organisation": "Example Academy", "recipient": "A. Rahman"},
    },
    "customization.notice": {
        "format": "html",
        "subject": False,
        "max_output": 100_000,
        "variables": {
            "organisation": "Organisation name",
            "title": "Title",
            "items": "List of lines",
        },
        "sample": {"organisation": "Example Academy", "title": "Notice", "items": ["One", "Two"]},
    },
}
