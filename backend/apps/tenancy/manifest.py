"""tenancy module manifest: tenant-scope permissions (Phase 3 plan §12.3; M4).

The tenant-scope codes (M4), the support-session codes (M5) and the platform code
``tenancy.support_session.request`` (P6, M5) and the registry codes of P4, P5 and P8 (M8:
``tenancy.tenant.view_any|create|update_any|suspend``, ``tenancy.limit.override``) are
registered here. Platform codes only ever apply to the platform host (ADR-033).

``support_readable`` (M5) marks the view codes an approved support session may use.

Flags (ADR-035): member and role management needs MFA; removing a member and other
privilege-changing or destructive actions also need a fresh step-up.
"""

from typing import Any


def _p(
    code: str,
    description: str,
    *,
    mfa: bool = False,
    step_up: bool = False,
    support: bool = False,
) -> dict[str, Any]:
    return {
        "code": code,
        "description": description,
        "requires_mfa": mfa or step_up,
        "requires_step_up": step_up,
        "support_readable": support,
    }


PERMISSIONS = [
    _p("tenancy.tenant.view", "View the organisation profile", support=True),
    _p("tenancy.tenant.update", "Update the organisation profile and settings", mfa=True),
    _p("tenancy.institution.view", "View institutions", support=True),
    _p("tenancy.institution.create", "Create institutions", mfa=True),
    _p("tenancy.institution.update", "Update institutions", mfa=True),
    _p("tenancy.institution.archive", "Archive institutions", step_up=True),
    _p("tenancy.campus.view", "View campuses", support=True),
    _p("tenancy.campus.create", "Create campuses", mfa=True),
    _p("tenancy.campus.update", "Update campuses", mfa=True),
    _p("tenancy.campus.archive", "Archive campuses", step_up=True),
    _p("tenancy.member.view", "View members", support=True),
    _p("tenancy.member.invite", "Invite members", mfa=True),
    _p("tenancy.member.update", "Suspend or reactivate members", mfa=True),
    _p("tenancy.member.remove", "Remove members", step_up=True),
    # Support sessions (Phase 3 M5; plan §11, ADR-045). Approving lets platform staff read
    # tenant data, so it needs a fresh step-up; the support codes are never support-readable.
    _p("tenancy.support_session.view", "View support sessions and their history", mfa=True),
    _p("tenancy.support_session.approve", "Approve or reject support sessions", step_up=True),
    _p("tenancy.support_session.revoke", "Revoke support sessions", mfa=True),
    # Platform permission (platform operation P6): request, end and list own sessions.
    _p("tenancy.support_session.request", "Request support access to a tenant", step_up=True),
    # Platform registry permissions (Phase 3 M8; operations P4, P5, P8). Registry fields only:
    # none of them gives access to tenant data (D8).
    _p("tenancy.tenant.view_any", "View the tenant registry", mfa=True),
    _p("tenancy.tenant.create", "Provision tenants and send owner invitations", mfa=True),
    _p("tenancy.tenant.update_any", "Update tenant registry fields", mfa=True),
    _p("tenancy.tenant.suspend", "Suspend or reactivate tenants", step_up=True),
    _p("tenancy.limit.override", "Override tenant institution and campus limits", step_up=True),
]

# Phase 4 M1 (ADR-050): this app's entry in the module catalogue.
MODULE = {
    "code": "tenancy",
    "name": "Tenancy",
    "category": "platform",
    "version": "1.0.0",
    "dependencies": ["identity", "rbac"],
    "sellable": False,
}

# Declared configuration keys (Phase 5 M1; ADR-057). No country-specific defaults.
SETTINGS = {
    "tenancy.week_start": {
        "description": "First day of the week (ISO 8601: 1 = Monday … 7 = Sunday)",
        "schema": {"type": "integer", "minimum": 1, "maximum": 7},
        "default": 1,
        "scopes": ["tenant", "institution", "campus"],
    },
    "tenancy.academic_year_start_month": {
        "description": "Month in which the academic year starts (1-12)",
        "schema": {"type": "integer", "minimum": 1, "maximum": 12},
        "default": 1,
        "scopes": ["tenant", "institution"],
    },
}

# Entities that accept custom fields (Phase 5 M3; CUSTOMIZATION_ENGINE.md §4.2). Values are
# stored in the entity's ``extra`` JSONB and validated against the active definitions.
CUSTOM_FIELD_ENTITIES = {
    "tenancy.institution": {"label": "Institution"},
    "tenancy.campus": {"label": "Campus"},
    "tenancy.member": {"label": "Member"},
}
