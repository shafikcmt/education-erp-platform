"""Accepted application → student (Phase 7 M4; ADR-065, ADR-074 Q4; plan §6).

Admissions calls :func:`on_application_accepted` after the acceptance commits
(``ADMISSIONS_ACCEPTED_HANDLERS``). It queues the tenant task ``students.convert_application``,
which runs :func:`convert` in that tenant's own transaction:

* the **student**, from the application's values (name, email, phone, date of birth) and the
  custom values whose keys match the tenant's student fields; values that don't validate for a
  student are left out rather than failing the conversion;
* the **guardian**, from ``guardian_name`` / ``guardian_phone``, matched by phone within the
  tenant before a new one is created (ADR-074 Q8), linked as the primary guardian;
* the **enrollment**, at once when the admitted unit has no units below it and the year is open;
  otherwise staff choose the section later (ADR-074 Q4).

Idempotent: one student per application (also a database constraint). The admission decision
authorises the conversion, so the task runs without a member; staff can run it again for one
application (``students.student.manage``), for example after raising the plan's student limit.
A conversion that fails validation (the plan limit, say) is audited and leaves the application
accepted.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest

from apps.audit.models import ActorType
from apps.audit.services import record
from apps.core.people import validate_person
from apps.students import services
from apps.students.models import Student

logger = logging.getLogger(__name__)


def on_application_accepted(*, tenant_id: str, application_id: str) -> None:
    """``ADMISSIONS_ACCEPTED_HANDLERS`` entry: queue the conversion for this tenant."""
    from apps.students.tasks import convert_application
    from apps.tenancy.tasking import TenantTaskRefused

    try:
        convert_application.delay(tenant_id=tenant_id, application_id=application_id)
    except TenantTaskRefused:  # run eagerly for a tenant without ``students``: nothing to do
        logger.info("students.conversion_skipped", extra={"tenant_id": tenant_id})


def _student_values(data: dict[str, Any]) -> dict[str, Any]:
    """The application's personal values that validate for a student (one by one)."""
    core: dict[str, Any] = {}
    candidates = {
        "name": data["name"], "email": data["email"], "phone": data["phone"],
        "date_of_birth": data["date_of_birth"],
    }  # fmt: skip
    for key, value in candidates.items():
        if value in (None, ""):
            continue
        try:
            core.update(validate_person({key: value}, services.STUDENT_FIELDS))
        except ValidationError:
            continue  # e.g. a phone written in a way the student record doesn't accept
    return core


def _custom_values(extra: dict[str, Any]) -> dict[str, Any]:
    """Custom values whose keys are student fields and that validate for a student."""
    from apps.customization.fields import validate_values
    from apps.customization.models import FieldDefinition

    keys = set(
        FieldDefinition.objects.filter(
            entity=services.STUDENT_ENTITY, deprecated_at__isnull=True
        ).values_list("key", flat=True)
    )
    out: dict[str, Any] = {}
    for key, value in extra.items():
        if key not in keys:
            continue
        try:
            out.update(validate_values(services.STUDENT_ENTITY, {key: value}, partial=True))
        except ValidationError:
            continue
    return out


def _number(data: dict[str, Any], institution: Any) -> str:
    """The Studio sequence when defined (empty: ``insert_student`` allocates); otherwise the
    application number when free, else a number derived from the application id."""
    from apps.customization.models import NumberingSequence

    if NumberingSequence.objects.filter(
        key=services.NUMBER_SEQUENCE, archived_at__isnull=True
    ).exists():
        return ""
    number = str(data["number"] or "")
    if number and not Student.objects.filter(institution=institution, number=number).exists():
        return number
    return f"APP-{data['id'].hex[-12:]}"


def _guardian(student: Student, core: dict[str, Any]) -> bool:
    phone, name = core.get("guardian_phone") or "", str(core.get("guardian_name") or "").strip()
    try:
        values = validate_person({"phone": phone, "name": name or "-"}, services.GUARDIAN_FIELDS)
        if not values.get("phone"):
            return False
        if not name:
            values.pop("name")
        guardian, _ = services.find_or_create_guardian(values, {})
        services.attach_guardian(student, guardian, relation="guardian", is_primary=True)
    except ValidationError:
        return False  # no usable phone, or no name for a new guardian: staff link one later
    return True


def _enrollment(student: Student, data: dict[str, Any]) -> bool:
    try:
        with transaction.atomic():
            services.insert_enrollment(student, year=data["year_id"], unit=data["unit_id"])
    except ValidationError:
        return False  # a class with sections, or a closed year: staff choose later
    return True


def _audit(action: str, actor: Any, request: HttpRequest | None, target: Any, **meta: Any) -> None:
    record(
        action,
        actor=actor,
        actor_type=ActorType.USER if actor is not None else ActorType.SYSTEM,
        request=request,
        target_type="students.student" if isinstance(target, Student) else "admissions.application",
        target_id=target.pk,
        metadata=meta,
    )


@transaction.atomic
def convert(
    application_id: Any,
    *,
    actor: Any = None,
    request: HttpRequest | None = None,
    raise_errors: bool = False,
) -> Student | None:
    """The student of an accepted application, created on first call. ``None`` when the
    application isn't accepted, or when the conversion fails and ``raise_errors`` is false."""
    from apps.admissions.selectors import accepted_application
    from apps.tenancy.models import Institution

    existing = Student.objects.filter(source_application_id=application_id).first()
    if existing is not None:
        return existing
    data = accepted_application(application_id)
    if data is None:
        return None
    institution = Institution.objects.get(pk=data["institution_id"])
    if actor is not None:
        services.require_manage(actor, institution.pk)
    try:
        with transaction.atomic():
            student = services.insert_student(
                institution=institution, core=_student_values(data),
                custom=_custom_values(data["extra"]), number=_number(data, institution),
                source_application_id=data["id"], created_by=getattr(actor, "pk", None),
            )  # fmt: skip
    except IntegrityError:  # converted concurrently: the other transaction won
        return Student.objects.filter(source_application_id=application_id).first()
    except ValidationError as exc:
        reason = next(iter(getattr(exc, "message_dict", {"error": None})), "error")
        _audit("students.student.conversion_failed", actor, request, _Ref(data["id"]),
               reason=reason)  # fmt: skip
        if raise_errors:
            raise
        return None
    student = Student.objects.select_for_update().get(pk=student.pk)
    guardian = _guardian(student, data["core"])
    enrolled = _enrollment(student, data)
    _audit("students.student.converted", actor, request, student, ref=student.number,
           guardian=guardian, enrolled=enrolled)  # fmt: skip
    return student


class _Ref:
    """An audit target by id only (the application lives in ``admissions``)."""

    def __init__(self, pk: Any) -> None:
        self.pk = pk
