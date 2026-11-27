"""parent_portal manifest (Phase 7 M8; ADR-069).

The guardian and student portal: a home with a child switcher, each child's profile and
enrollment (read-only) and their timetable. Attendance, results, fees and notices plug in
during Phases 8-14. No tables of its own: it reads ``students`` (and ``timetable`` when the
tenant has it) through their selectors.
"""

MODULE = {
    "code": "parent_portal",
    "name": "Parent portal",
    "category": "standard",
    "version": "1.0.0",
    "dependencies": ["students"],
    "sellable": True,
}

PERMISSIONS = [
    {"code": "parent_portal.portal.use", "description": "Use the guardian or student portal"},
]
