"""timetable manifest (Phase 7 M7; ADR-071, ADR-066).

Bell schedules and periods per institution, rooms, and weekly slots (a unit, a period, an
offering with its teacher, a room). Clashes (one unit, one teacher, one room per weekday and
period) are refused, backed by unique constraints. No substitutions and no automatic generation
in Phase 7.
"""

MODULE = {
    "code": "timetable",
    "name": "Timetable",
    "category": "standard",
    "version": "1.0.0",
    "dependencies": ["academics", "staff"],
    "sellable": True,
}

PERMISSIONS = [
    {"code": "timetable.timetable.view", "description": "View timetables"},
    {
        "code": "timetable.timetable.manage",
        "description": "Manage bell schedules, rooms and timetable slots",
        "requires_mfa": True,
    },
]
