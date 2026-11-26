"""Reads other modules use (Phase 7 M4): ``students`` converts accepted applications through
:func:`accepted_application` instead of reading admissions tables."""

from __future__ import annotations

from typing import Any

from apps.admissions.models import Application, Cycle, CycleTarget


def accepted_application(application_id: Any) -> dict[str, Any] | None:
    """The values of an accepted application of the current tenant, or ``None``."""
    row = Application.objects.filter(pk=application_id, status=Application.Status.ACCEPTED).first()
    if row is None:
        return None
    cycle = Cycle.objects.get(pk=row.cycle_id)
    target = CycleTarget.objects.get(pk=row.target_id)
    return {
        "id": row.pk,
        "institution_id": row.institution_id,
        "number": row.number,
        "name": row.applicant_name,
        "email": row.applicant_email,
        "phone": row.applicant_phone,
        "date_of_birth": row.date_of_birth,
        "core": dict(row.core),
        "extra": dict(row.extra),
        "year_id": cycle.year_id,
        "unit_id": target.unit_id,
    }
