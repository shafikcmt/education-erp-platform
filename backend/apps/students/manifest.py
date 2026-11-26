"""students manifest (Phase 7; ADR-068, ADR-069, ADR-073, ADR-074).

Student profiles, guardians (N-N), enrollments in the Phase 6 unit tree, documents (``files``),
lifecycle (transfer, promotion, transfer certificate, alumni) and bulk import. Relationship
scopes: staff see students in their institution scope, teachers only the students they teach
(``view_assigned``), guardians only their own children, students only themselves.
"""

MODULE = {
    "code": "students",
    "name": "Students",
    "category": "standard",
    "version": "1.0.0",
    "dependencies": ["academics", "customization"],
    "sellable": True,
}

PERMISSIONS = [
    {"code": "students.student.view", "description": "View students in your scope"},
    {
        "code": "students.student.view_assigned",
        "description": "View the students you teach or advise",
    },
    {
        "code": "students.student.manage",
        "description": "Create and change students, guardians and enrollments",
        "requires_mfa": True,
    },
    {
        "code": "students.student.import",
        "description": "Import students in bulk",
        "requires_mfa": True,
        "requires_step_up": True,
    },
    {
        "code": "students.student.promote",
        "description": "Promote students at the end of a year",
        "requires_mfa": True,
        "requires_step_up": True,
    },
    {
        "code": "students.student.transfer",
        "description": "Transfer or withdraw students and issue transfer certificates",
        "requires_mfa": True,
    },
    {"code": "students.guardian.view", "description": "View guardians of students in scope"},
    {
        "code": "students.guardian.manage",
        "description": "Create, link and merge guardians",
        "requires_mfa": True,
    },
    {"code": "students.child.view", "description": "View your own children (guardians)"},
    {"code": "students.profile.view_own", "description": "View your own student profile"},
    {"code": "students.document.view", "description": "View student documents in scope"},
    {
        "code": "students.document.upload",
        "description": "Upload student documents",
        "requires_mfa": True,
    },
]

CUSTOM_FIELD_ENTITIES = {
    "students.student": {
        "label": "Student",
        "core_fields": ["name", "date_of_birth", "gender", "email", "phone"],
    },
    "students.guardian": {
        "label": "Guardian",
        "core_fields": ["name", "phone", "email"],
    },
}
FILE_PURPOSES = {
    "students.document": {
        "types": ["application/pdf", "image/jpeg", "image/png"],
        "max_bytes": 10 * 1024 * 1024,
        "max_per_owner": 30,
        "applicant_visible": False,
    },
}

# Phase 7 M5 (ADR-074 Q5): printable HTML documents rendered from Studio templates (sandboxed,
# ADR-056). Server PDF arrives in Phase 9.
_STUDENT_VARIABLES = {
    "institution": "Institution name",
    "name": "Student name",
    "number": "Student number",
    "date_of_birth": "Date of birth",
    "unit": "Current class or section",
    "year": "Current academic year",
    "issued_on": "Date of issue",
}
_STUDENT_SAMPLE = {
    "institution": "Example Academy", "name": "A. Rahman", "number": "STU-0001",
    "date_of_birth": "2015-02-01", "unit": "Six A", "year": "2027", "issued_on": "2027-06-30",
}  # fmt: skip
TEMPLATE_KINDS = {
    "students.id_card": {
        "format": "html",
        "subject": False,
        "max_output": 20_000,
        "variables": {**_STUDENT_VARIABLES, "guardian_phone": "Primary guardian's phone"},
        "sample": {**_STUDENT_SAMPLE, "guardian_phone": "01711000000"},
    },
    "students.transfer_certificate": {
        "format": "html",
        "subject": False,
        "max_output": 50_000,
        "variables": {
            **_STUDENT_VARIABLES,
            "certificate_number": "Transfer certificate number",
            "reason": "Reason for leaving",
            "destination": "Institution the student goes to",
            "admitted_on": "Date of first enrollment",
        },
        "sample": {
            **_STUDENT_SAMPLE,
            "certificate_number": "TC-2027-0001",
            "reason": "Family moved",
            "destination": "City School",
            "admitted_on": "2025-01-01",
        },
    },
}
FILE_PURPOSES["students.import"] = {  # Phase 7 M6: bulk import files (CSV or XLSX)
    "types": ["text/csv", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"],
    "max_bytes": 5 * 1024 * 1024,
    "max_per_owner": 1,
    "applicant_visible": False,
}
