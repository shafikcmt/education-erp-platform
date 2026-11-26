"""staff manifest (Phase 7 M3; ADR-070, ADR-073).

Staff profiles (with or without a login), departments and designations per institution, and
class-teacher advisors per unit and year. Staff see profiles in their scope; everyone with a
profile sees their own (``staff.profile.view_own``).
"""

MODULE = {
    "code": "staff",
    "name": "Staff",
    "category": "standard",
    "version": "1.0.0",
    "dependencies": ["academics"],
    "sellable": True,
}

PERMISSIONS = [
    {"code": "staff.profile.view", "description": "View staff profiles in your scope"},
    {
        "code": "staff.profile.manage",
        "description": "Create and change staff profiles",
        "requires_mfa": True,
    },
    {"code": "staff.profile.view_own", "description": "View your own staff profile"},
    {
        "code": "staff.structure.manage",
        "description": "Manage departments and designations",
        "requires_mfa": True,
    },
]

CUSTOM_FIELD_ENTITIES = {
    "staff.profile": {
        "label": "Staff",
        "core_fields": ["name", "gender", "email", "phone", "joining_date"],
    },
}
