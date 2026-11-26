"""The ``staff`` import kind (Phase 7 M6; ADR-072): staff profiles with their department and
designation by code. Registered in ``STUDENTS_IMPORT_KINDS``; the engine lives in
``students.imports`` and loads this class by path."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError

from apps.staff import services
from apps.staff.models import Department, Designation

FIELDS = frozenset({
    "number", "name", "gender", "email", "phone", "joining_date", "department", "designation",
    "employment_type",
})  # fmt: skip


def _by_code(model: Any, institution: Any, code: str, field: str) -> Any:
    if not code:
        return None
    row = model.objects.filter(
        institution_id=institution.pk, code=code, archived_at__isnull=True
    ).first()
    if row is None:
        raise ValidationError({field: f"No {field} with the code {code!r}."})
    return row


class StaffRows:
    permission = services.MANAGE
    fields = FIELDS
    custom_entity = services.ENTITY

    def check_options(self, institution: Any, options: dict[str, Any]) -> dict[str, Any]:
        return {}

    def apply(
        self, actor: Any, institution: Any, values: dict[str, str], options: dict[str, Any]
    ) -> Any:
        from apps.students.imports import coerce_custom, split

        core, custom = split(values)
        person = {k: v for k in ("name", "gender", "email", "phone", "joining_date")
                  if (v := core.get(k, ""))}  # fmt: skip
        profile = services.create_profile(
            actor=actor, institution=institution, values=person,
            extra=coerce_custom(self.custom_entity, custom), number=core.get("number", ""),
            department=_by_code(Department, institution, core.get("department", ""), "department"),
            designation=_by_code(
                Designation, institution, core.get("designation", ""), "designation"
            ),
            employment_type=core.get("employment_type") or "permanent",
        )  # fmt: skip
        return profile.pk
