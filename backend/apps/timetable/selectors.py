"""Who sees which timetables (Phase 7 M7; ADR-071, ADR-073).

* **Staff** (``timetable.timetable.view`` and ``academics.structure.view`` in the institution or
  one of its campuses) see every unit's, teacher's and room's timetable there.
* **Portal members** (guardians, students: ``timetable.timetable.view`` without the structure
  code) see only the units their children or they themselves are actively enrolled in. Those
  units come from ``TIMETABLE_PORTAL_UNITS`` (``students`` registers them), so ``timetable``
  never imports ``students``.
* **Teachers** see their own lessons (``my_slots``).
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db.models import QuerySet
from django.utils.module_loading import import_string
from rest_framework.exceptions import NotFound

from apps.timetable.models import Slot

VIEW = "timetable.timetable.view"
STRUCTURE_VIEW = "academics.structure.view"


def staff_view(actor: Any, institution_id: Any) -> bool:
    from apps.tenancy.api.permissions import visible_institution

    try:
        visible_institution(actor, VIEW, institution_id)
        visible_institution(actor, STRUCTURE_VIEW, institution_id)
    except NotFound:
        return False
    return True


def portal_units(actor: Any) -> set[Any]:
    units: set[Any] = set()
    for path in getattr(settings, "TIMETABLE_PORTAL_UNITS", []):
        units |= set(import_string(path)(actor))
    return units


def slots() -> QuerySet[Slot]:
    from apps.academics.models import AcademicYear

    return (
        Slot.objects.exclude(year__status=AcademicYear.Status.CLOSED)
        .select_related("period", "unit", "room", "offering__subject")
        .order_by("weekday", "period__start_time")
    )


def my_slots(actor: Any) -> QuerySet[Slot]:
    from apps.tenancy.models import Membership

    mine = Membership.objects.filter(user_id=actor.pk, status=Membership.Status.ACTIVE).values("pk")
    return slots().filter(teacher_id__in=mine)
