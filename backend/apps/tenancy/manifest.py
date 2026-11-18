"""tenancy module manifest: tenant-scope permissions (Phase 3 plan §12.3; M4).

Only the tenant-scope codes that M4 evaluates are registered here. The platform codes
(``tenancy.tenant.view_any|create|update_any|suspend``, ``tenancy.limit.override``) and the
support-session codes are registered by the milestones that implement them (M5, M8): until a
code exists, every platform operation that needs it fails closed (plan §24.1 N3).

Flags (ADR-035): member and role management needs MFA; removing a member and other
privilege-changing or destructive actions also need a fresh step-up.
"""

from typing import Any


def _p(code: str, description: str, *, mfa: bool = False, step_up: bool = False) -> dict[str, Any]:
    return {
        "code": code,
        "description": description,
        "requires_mfa": mfa or step_up,
        "requires_step_up": step_up,
    }


PERMISSIONS = [
    _p("tenancy.tenant.view", "View the organisation profile"),
    _p("tenancy.tenant.update", "Update the organisation profile and settings", mfa=True),
    _p("tenancy.institution.view", "View institutions"),
    _p("tenancy.institution.create", "Create institutions", mfa=True),
    _p("tenancy.institution.update", "Update institutions", mfa=True),
    _p("tenancy.institution.archive", "Archive institutions", step_up=True),
    _p("tenancy.campus.view", "View campuses"),
    _p("tenancy.campus.create", "Create campuses", mfa=True),
    _p("tenancy.campus.update", "Update campuses", mfa=True),
    _p("tenancy.campus.archive", "Archive campuses", step_up=True),
    _p("tenancy.member.view", "View members"),
    _p("tenancy.member.invite", "Invite members", mfa=True),
    _p("tenancy.member.update", "Suspend or reactivate members", mfa=True),
    _p("tenancy.member.remove", "Remove members", step_up=True),
]
