"""academics manifest (Phase 6 M1; ADR-063).

Academic years and terms, the configurable unit tree (levels from the effective
``customization.structure_levels``), subjects/courses and offerings. Institution admins and
academic coordinators manage them in their scope; teachers read the structure.
"""

MODULE = {
    "code": "academics",
    "name": "Academics",
    "category": "standard",
    "version": "1.0.0",
    "dependencies": ["customization"],
    "sellable": True,
}

PERMISSIONS = [
    {"code": "academics.year.view", "description": "View academic years and terms"},
    {
        "code": "academics.year.manage",
        "description": "Create and change academic years and terms",
        "requires_mfa": True,
    },
    {"code": "academics.structure.view", "description": "View the academic structure"},
    {
        "code": "academics.structure.manage",
        "description": "Create, change and archive academic units",
        "requires_mfa": True,
    },
    {"code": "academics.subject.view", "description": "View subjects and courses"},
    {
        "code": "academics.subject.manage",
        "description": "Create, change and archive subjects and courses",
        "requires_mfa": True,
    },
    {"code": "academics.offering.view", "description": "View offerings and their teachers"},
    {
        "code": "academics.offering.manage",
        "description": "Create offerings and assign teachers",
        "requires_mfa": True,
    },
]

# Promotion rules can be drafted and tested now; they run once students exist (Phase 7).
RULE_NAMESPACES = {
    "academics.promotion": {
        "description": "Promote a student when the rule is true",
        "variables": ["student.*", "today"],
        "result": "boolean",
    },
}
