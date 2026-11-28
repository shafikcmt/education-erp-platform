"""attendance manifest (Phase 8; ADR-076 to ADR-080).

Daily and period registers per unit with per-student records, staff daily records and leave
requests. Teachers mark the registers of the units they advise or the offerings they teach
(ADR-073 assigned scope); ``attendance.record.manage`` marks any register in scope, edits past
the edit window and unlocks. Modes, edit window, lock, threshold and alerts are Studio settings
resolved Core -> preset -> tenant -> institution -> campus (ADR-057).
"""

MODULE = {
    "code": "attendance",
    "name": "Attendance",
    "category": "standard",
    "version": "1.0.0",
    "dependencies": ["students", "staff"],
    "sellable": True,
}

PERMISSIONS = [
    {
        "code": "attendance.record.mark",
        "description": "Mark the registers of the units and offerings one teaches or advises",
    },
    {"code": "attendance.record.view", "description": "View attendance registers in scope"},
    {
        "code": "attendance.record.manage",
        "description": "Mark any register in scope, edit past the edit window and unlock",
        "requires_mfa": True,
    },
    {"code": "attendance.report.view", "description": "View attendance reports and exports"},
    {
        "code": "attendance.staff.mark",
        "description": "Mark the staff daily register",
        "requires_mfa": True,
    },
    {"code": "attendance.staff.view", "description": "View staff attendance in scope"},
    {
        "code": "attendance.leave.request",
        "description": "Request leave for oneself or one's children",
    },
    {"code": "attendance.leave.review", "description": "Approve or reject leave requests"},
]

_SCOPES = ["tenant", "institution", "campus"]

# Declared configuration keys (ADR-057, plan §3). Presets v3 set ``attendance.mode`` per type.
SETTINGS = {
    "attendance.mode": {
        "description": "Which registers are taken: daily, period or both",
        "schema": {"type": "string", "enum": ["daily", "period", "both"]},
        "default": "daily",
        "scopes": _SCOPES,
    },
    "attendance.default_status": {
        "description": "The status the quick-mark screen starts with",
        "schema": {"type": "string", "enum": ["present", "absent"]},
        "default": "present",
        "scopes": _SCOPES,
    },
    "attendance.edit_window_days": {
        "description": "Days after the date during which the marker may still edit",
        "schema": {"type": "integer", "minimum": 0, "maximum": 60},
        "default": 3,
        "scopes": _SCOPES,
    },
    "attendance.lock_after_days": {
        "description": "Days after which registers lock (unlocking needs a reason)",
        "schema": {"type": "integer", "minimum": 1, "maximum": 365},
        "default": 30,
        "scopes": _SCOPES,
    },
    "attendance.threshold_percent": {
        "description": "Students below this attendance percentage are flagged",
        "schema": {"type": "integer", "minimum": 0, "maximum": 100},
        "default": 75,
        "scopes": _SCOPES,
    },
    "attendance.alert_guardians": {
        "description": "Notify guardians with portal logins when a child is absent",
        "schema": {"type": "boolean"},
        "default": True,
        "scopes": _SCOPES,
    },
    "attendance.alert_email": {
        "description": "Also email absence alerts to guardians",
        "schema": {"type": "boolean"},
        "default": False,
        "scopes": _SCOPES,
    },
}
