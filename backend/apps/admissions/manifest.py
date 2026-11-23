"""admissions manifest (Phase 6 M4; ADR-063, ADR-065, ADR-066).

Inquiries, admission cycles bound to Studio artefacts (form, workflow, merit rule, numbering),
applications and their review, the public application flow (M5), admission tests and the
merit list (M6). Applicant data is personal data: visible only with ``admissions.application.view``
in the institution's scope.
"""

MODULE = {
    "code": "admissions",
    "name": "Admissions",
    "category": "standard",
    "version": "1.0.0",
    "dependencies": ["academics", "customization"],
    "sellable": True,
}

PERMISSIONS = [
    {"code": "admissions.inquiry.view", "description": "View admission inquiries"},
    {"code": "admissions.inquiry.manage", "description": "Record and follow up inquiries"},
    {"code": "admissions.cycle.view", "description": "View admission cycles"},
    {
        "code": "admissions.cycle.manage",
        "description": "Create, open and close admission cycles",
        "requires_mfa": True,
    },
    {"code": "admissions.application.view", "description": "View applications (personal data)"},
    {
        "code": "admissions.application.review",
        "description": "Enter applications and move them through review",
        "requires_mfa": True,
    },
    {
        "code": "admissions.application.decide",
        "description": "Offer or reject applications and record offer responses",
        "requires_mfa": True,
    },
    # Phase 6 M6
    {
        "code": "admissions.test.manage",
        "description": "Schedule admission tests, seat applicants and enter scores",
        "requires_mfa": True,
    },
    {
        "code": "admissions.merit.publish",
        "description": "Publish a merit list (offers follow its ranks)",
        "requires_mfa": True,
        "requires_step_up": True,
    },
]

# The application form is a Studio form on this entity (core fields below plus custom fields).
CUSTOM_FIELD_ENTITIES = {
    "admissions.application": {
        "label": "Application",
        "core_fields": [
            "applicant_name",
            "applicant_email",
            "applicant_phone",
            "date_of_birth",
            "guardian_name",
            "guardian_phone",
            "previous_institution",
            "address",
        ],
    },
}
WORKFLOW_SUBJECTS = {"admissions.application": {"label": "Application"}}
RULE_NAMESPACES = {
    "admissions.merit": {
        "description": "Merit score of an evaluated application (higher ranks first)",
        "variables": ["application.*", "today"],
        "result": "number",
    },
}
FILE_PURPOSES = {
    "admissions.document": {
        "types": ["application/pdf", "image/jpeg", "image/png"],
        "max_bytes": 5 * 1024 * 1024,
        "max_per_owner": 5,
        "applicant_visible": True,
    },
}
