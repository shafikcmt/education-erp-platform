"""Modules that are planned but not built yet (Phase 4 M1; ADR-050; `MODULE_CATALOG.md` §1).

Plans and add-ons may reference a module before its code exists. These entries are synced
with ``available = False``: such a module can be packaged, but nobody can be entitled to it
until its app ships a manifest (the app's own ``MODULE`` then replaces the entry here).

Dependencies follow `MODULE_CATALOG.md` §1. "All entitled modules" (reports, AI) is not a
dependency: those modules adapt to what the tenant has.
"""

from typing import Any

PLATFORM, STANDARD, EXTENSION = "platform", "standard", "extension"


def _m(
    code: str, name: str, category: str, deps: tuple[str, ...] = (), sellable: bool = False
) -> dict[str, Any]:
    return {
        "code": code,
        "name": name,
        "category": category,
        "dependencies": list(deps),
        "sellable": sellable,
        "version": "0.0.0",
    }


PLANNED_MODULES: list[dict[str, Any]] = [
    _m("files", "Files", PLATFORM, ("tenancy",)),
    _m("notifications_core", "Notifications", PLATFORM, ("tenancy",)),
    _m("academics", "Academics", STANDARD, ("customization",), True),
    _m("timetable", "Timetable", STANDARD, ("academics", "staff"), True),
    _m("admissions", "Admissions", STANDARD, ("academics", "customization"), True),
    _m("students", "Students", STANDARD, ("academics",), True),
    _m("staff", "Staff", STANDARD, ("academics",), True),
    _m("parent_portal", "Parent portal", STANDARD, ("students",), True),
    _m("attendance", "Attendance", STANDARD, ("students", "staff"), True),
    _m("examinations", "Examinations", STANDARD, ("academics", "students"), True),
    # The ledger posting engine is always installed (ADR-025, Proposed): fees needs students only.
    _m("fees", "Fees", STANDARD, ("students",), True),
    _m("accounting", "Accounting", STANDARD, ("tenancy",), True),
    _m("hr_payroll", "HR and payroll", STANDARD, ("staff", "accounting"), True),
    _m("hostel", "Hostel", STANDARD, ("students", "fees", "attendance"), True),
    _m("transport", "Transport", STANDARD, ("students", "fees"), True),
    _m("library", "Library", STANDARD, ("students", "staff"), True),
    _m("lms", "LMS", STANDARD, ("academics", "students", "staff"), True),
    _m("online_exams", "Online exams", STANDARD, ("academics", "students"), True),
    _m("communication", "Communication", STANDARD, ("notifications_core",), True),
    _m("reports_analytics", "Reports and analytics", STANDARD, (), True),
    _m("ai_assistant", "AI assistant", STANDARD, ("module_registry", "rbac"), True),
    _m("custom_module_builder", "Custom module builder", EXTENSION, ("customization",), True),
    _m("ext_hifz_tracking", "Hifz tracking", EXTENSION, ("students", "academics"), True),
    _m(
        "ext_course_registration",
        "Course registration",
        EXTENSION,
        ("academics", "students", "fees"),
        True,
    ),
    _m("ext_batch_management", "Batch management", EXTENSION, ("academics", "fees"), True),
    _m("ext_certification", "Certification", EXTENSION, ("academics", "examinations"), True),
]
