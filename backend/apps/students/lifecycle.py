"""Student lifecycle: moving within a year, withdrawal, transfer certificates, promotion,
alumni and printable documents (Phase 7 M5; ADR-068, ADR-074 Q5; plan §2).

* **Move** (``students.student.manage``): the active enrollment of the year ends (status
  ``transferred``) and a new one starts in another leaf unit of the same year.
* **Withdraw** and **transfer certificate** (``students.student.transfer``): the student leaves;
  active enrollments end. A certificate gets a number from the Studio sequence
  ``transfer_certificate`` (or one given by staff), a reason and a destination.
* **Promotion** (``students.student.promote``, step-up at the API): for the active enrollments
  of a source unit and year, a preview suggests *promote* or *repeat* from the published
  ``academics.promotion`` rule when one is named (variables ``student.*`` and ``today``), and
  *complete* when there is no next unit (the final level). Staff confirm each decision; applying
  runs in one transaction: the old enrollment ends as promoted, repeated or completed, the next
  one starts in the target (or the same) unit of the next year, and completion makes the
  student **alumni**.
* **Documents** (``students.student.view`` in the institution): an ID card and a transfer
  certificate rendered from published Studio templates of the kinds ``students.id_card`` and
  ``students.transfer_certificate`` (sandboxed HTML; server PDF in Phase 9).

Personal data never goes into audit metadata.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.students import services
from apps.students.models import Enrollment, Student, StudentGuardian, TransferCertificate

if TYPE_CHECKING:
    from apps.identity.models import User

TRANSFER, PROMOTE = "students.student.transfer", "students.student.promote"
VIEW = "students.student.view"
TC_SEQUENCE = "transfer_certificate"
PROMOTION_NAMESPACE = "academics.promotion"
ACTIONS = ("promote", "repeat", "complete")
ID_CARD, TC_KIND = "students.id_card", "students.transfer_certificate"


def _today() -> dt.date:
    return timezone.localdate()


def _end_active(student: Student, status: str, on: dt.date) -> int:
    rows = Enrollment.objects.filter(student=student, status=Enrollment.Status.ACTIVE)
    for row in rows:
        row.status, row.end_date = status, max(on, row.start_date)
        row.save(update_fields=["status", "end_date", "updated_at"])
    return len(rows)


def _reason(text: Any, *, required: bool = True) -> str:
    value = str(text or "").strip()
    if required and not value:
        raise ValidationError({"reason": "Give a reason."})
    if len(value) > 300:
        raise ValidationError({"reason": "At most 300 characters."})
    return value


# --------------------------------------------------------------------------- moving and leaving
@transaction.atomic
def move(
    *,
    actor: User,
    student: Student,
    unit: Any,
    roll_number: str = "",
    request: HttpRequest | None = None,
) -> Enrollment:
    """Move a student to another leaf unit within the year of their active enrollment."""
    student = Student.objects.select_for_update().get(pk=student.pk)
    services.require_manage(actor, student.institution_id)
    current = (
        Enrollment.objects.select_for_update()
        .filter(student=student, status=Enrollment.Status.ACTIVE)
        .order_by("-start_date")
        .first()
    )
    if current is None:
        raise ValidationError({"student": "The student has no active enrollment to move."})
    if str(getattr(unit, "pk", unit)) == str(current.unit_id):
        raise ValidationError({"unit": "The student is already in this unit."})
    today = max(_today(), current.start_date)
    current.status, current.end_date = Enrollment.Status.TRANSFERRED, today
    current.save(update_fields=["status", "end_date", "updated_at"])
    row = services.insert_enrollment(
        student, year=current.year_id, unit=unit, roll_number=roll_number,
        start_date=today, created_by=actor.pk,
    )  # fmt: skip
    services._audit("students.enrollment.moved", actor, request, row)
    return row


def _leave(actor: User, student: Student) -> Student:
    student = Student.objects.select_for_update().get(pk=student.pk)
    services._authorise(actor, TRANSFER, student.institution_id)
    if student.status != Student.Status.ACTIVE:
        raise ValidationError({"student": "Only active students leave this way."})
    return student


@transaction.atomic
def withdraw(
    *,
    actor: User,
    student: Student,
    reason: str,
    on: dt.date | None = None,
    request: HttpRequest | None = None,
) -> Student:
    student = _leave(actor, student)
    _reason(reason)  # required, but free text stays out of the audit log
    _end_active(student, Enrollment.Status.WITHDRAWN, on or _today())
    student.status, student.updated_by = Student.Status.WITHDRAWN, actor.pk
    student.save(update_fields=["status", "updated_by", "updated_at"])
    services._audit("students.student.withdrawn", actor, request, student)
    return student


def _tc_number(institution_id: Any, number: str) -> str:
    from apps.customization import numbering
    from apps.customization.models import NumberingSequence
    from apps.tenancy.models import Institution

    number = number.strip()
    if number:
        if len(number) > 64:
            raise ValidationError({"number": "At most 64 characters."})
        if TransferCertificate.objects.filter(
            institution_id=institution_id, number=number
        ).exists():
            raise ValidationError({"number": "This certificate number is already used."})
        return number
    if not NumberingSequence.objects.filter(key=TC_SEQUENCE, archived_at__isnull=True).exists():
        raise ValidationError(
            {"number": "Give a number, or define the 'transfer_certificate' numbering sequence."}
        )
    return numbering.allocate(TC_SEQUENCE, institution=Institution.objects.get(pk=institution_id))


@transaction.atomic
def issue_transfer_certificate(
    *,
    actor: User,
    student: Student,
    reason: str,
    destination: str = "",
    number: str = "",
    on: dt.date | None = None,
    request: HttpRequest | None = None,
) -> TransferCertificate:
    student = _leave(actor, student)
    text, where = _reason(reason), str(destination or "").strip()
    if len(where) > 200:
        raise ValidationError({"destination": "At most 200 characters."})
    issued = on or _today()
    tc = TransferCertificate.objects.create(
        institution_id=student.institution_id, student=student,
        number=_tc_number(student.institution_id, number), reason=text, destination=where,
        issued_on=issued, created_by=actor.pk,
    )  # fmt: skip
    _end_active(student, Enrollment.Status.TRANSFERRED, issued)
    student.status, student.updated_by = Student.Status.TRANSFERRED, actor.pk
    student.save(update_fields=["status", "updated_by", "updated_at"])
    services._audit("students.student.transferred", actor, request, student, ref=tc.number)
    return tc


# --------------------------------------------------------------------------- promotion
def promotion_context(student: Student) -> dict[str, Any]:
    """The variables an ``academics.promotion`` rule may read (``student.*``, ``today``)."""
    context: dict[str, Any] = {"today": _today()}
    for key, value in (student.extra or {}).items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            context[f"student.{key}"] = value
    context.update(
        {
            "student.name": student.name,
            "student.number": student.number,
            "student.gender": student.gender,
            "student.date_of_birth": student.date_of_birth,
        }
    )
    # Other modules add variables by path (Phase 8: ``attendance.*``), so students never
    # imports them.
    from django.conf import settings
    from django.utils.module_loading import import_string

    for path in getattr(settings, "STUDENTS_PROMOTION_CONTEXT", []):
        context.update(import_string(path)(student))
    return context


def _promotion_frame(
    actor: User, year_from: Any, unit_from: Any, year_to: Any, unit_to: Any
) -> tuple[Any, Any, Any, Any]:
    from apps.academics.models import AcademicYear, Unit

    source_year = AcademicYear.objects.filter(pk=getattr(year_from, "pk", year_from)).first()
    if source_year is None:
        raise ValidationError({"year_from": "Unknown academic year."})
    inst = source_year.institution_id
    services._authorise(actor, PROMOTE, inst)
    source_unit = Unit.objects.filter(pk=getattr(unit_from, "pk", unit_from), institution_id=inst)
    source = source_unit.first()
    if source is None:
        raise ValidationError({"unit_from": "Choose a unit of this institution."})
    next_year = services._open_year(year_to, inst)
    if next_year.pk == source_year.pk or next_year.start_date <= source_year.start_date:
        raise ValidationError({"year_to": "Choose the next academic year."})
    target = services._leaf_unit(unit_to, inst) if unit_to not in (None, "") else None
    return source_year, source, next_year, target


def promotion_preview(
    *,
    actor: User,
    year_from: Any,
    unit_from: Any,
    year_to: Any,
    unit_to: Any = None,
    rule_key: str = "",
) -> list[dict[str, Any]]:
    """One row per active enrollment of the source unit and year, with a suggestion. Without
    a next unit every suggestion is *complete* (the final level)."""
    from apps.customization.rule_services import evaluate_published
    from apps.customization.rules import RuleError

    source_year, source, _, target = _promotion_frame(actor, year_from, unit_from, year_to,
                                                      unit_to)  # fmt: skip
    rows = (
        Enrollment.objects.filter(year=source_year, unit=source, status=Enrollment.Status.ACTIVE)
        .select_related("student")
        .order_by("roll_number", "student__name")
    )
    out = []
    for enrollment in rows:
        student = Student.objects.get(pk=enrollment.student_id)
        suggestion, note = "promote", ""
        if target is None:
            suggestion = "complete"
        elif rule_key:
            try:
                passed = evaluate_published(
                    rule_key, PROMOTION_NAMESPACE, promotion_context(student)
                )
                suggestion = "promote" if passed else "repeat"
            except (RuleError, ValidationError) as exc:
                suggestion, note = "repeat", str(exc)[:200]
        out.append({
            "student": student.pk, "name": student.name, "number": student.number,
            "roll_number": enrollment.roll_number, "suggestion": suggestion, "note": note,
        })  # fmt: skip
    return out


@transaction.atomic
def apply_promotion(
    *,
    actor: User,
    year_from: Any,
    unit_from: Any,
    year_to: Any,
    unit_to: Any = None,
    decisions: dict[str, str],
    request: HttpRequest | None = None,
) -> dict[str, int]:
    """Apply staff-confirmed decisions (``{student_id: promote|repeat|complete}``) in one
    transaction. Any invalid decision rolls everything back."""
    source_year, source, next_year, target = _promotion_frame(
        actor, year_from, unit_from, year_to, unit_to
    )
    if not decisions:
        raise ValidationError({"decisions": "Confirm at least one student."})
    counts = dict.fromkeys(ACTIONS, 0)
    errors: dict[str, str] = {}
    for student_id, action in decisions.items():
        if action not in ACTIONS or (action == "promote" and target is None):
            errors[str(student_id)] = "Choose promote (with a next unit), repeat or complete."
            continue
        enrollment = (
            Enrollment.objects.select_for_update()
            .filter(
                student_id=student_id,
                year=source_year,
                unit=source,
                status=Enrollment.Status.ACTIVE,
            )
            .first()
        )
        if enrollment is None:
            errors[str(student_id)] = "Not actively enrolled in this unit and year."
            continue
        student = Student.objects.select_for_update().get(pk=enrollment.student_id)
        status = {"promote": Enrollment.Status.PROMOTED, "repeat": Enrollment.Status.REPEATED,
                  "complete": Enrollment.Status.COMPLETED}[action]  # fmt: skip
        enrollment.status = status
        enrollment.end_date = max(source_year.end_date, enrollment.start_date)
        enrollment.save(update_fields=["status", "end_date", "updated_at"])
        if action == "complete":
            student.status, student.updated_by = Student.Status.ALUMNI, actor.pk
            student.save(update_fields=["status", "updated_by", "updated_at"])
        else:
            try:
                services.insert_enrollment(
                    student, year=next_year, unit=target if action == "promote" else source,
                    roll_number="", start_date=next_year.start_date, created_by=actor.pk,
                )  # fmt: skip
            except ValidationError as exc:
                errors[str(student_id)] = "; ".join(exc.messages)
                continue
        counts[action] += 1
    if errors:
        raise ValidationError(errors)
    services._audit("students.promotion.applied", actor, request, source, **counts)
    return counts


# --------------------------------------------------------------------------- documents
def _render(kind: str, template_key: str, locale: str, data: dict[str, Any]) -> str:
    from apps.customization import versioning
    from apps.customization.models import TemplateDefinition
    from apps.customization.template_services import render_published

    template = versioning.published(TemplateDefinition, template_key)
    if template is None or template.kind != kind:
        raise ValidationError({"template": f"Choose a published template of the kind {kind}."})
    return render_published(template_key, locale, data)["body"]


def _base(student: Student) -> dict[str, Any]:
    from apps.tenancy.models import Institution

    current = (
        Enrollment.objects.filter(student=student)
        .order_by("-start_date")
        .values_list("unit__name", "year__name")
        .first()
    )
    return {
        "institution": Institution.objects.get(pk=student.institution_id).name,
        "name": student.name,
        "number": student.number,
        "date_of_birth": student.date_of_birth.isoformat() if student.date_of_birth else "",
        "unit": current[0] if current else "",
        "year": current[1] if current else "",
        "issued_on": _today().isoformat(),
    }


def id_card(*, actor: User, student: Student, template_key: str, locale: str = "en") -> str:
    services._authorise(actor, VIEW, student.institution_id)
    phone = (
        StudentGuardian.objects.filter(student=student, is_primary=True)
        .values_list("guardian__phone", flat=True)
        .first()
    )
    data = {**_base(student), "guardian_phone": phone or ""}
    return _render(ID_CARD, template_key, locale, data)


def transfer_certificate_document(
    *, actor: User, certificate: TransferCertificate, template_key: str, locale: str = "en"
) -> str:
    student = Student.objects.get(pk=certificate.student_id)
    services._authorise(actor, VIEW, student.institution_id)
    first = Enrollment.objects.filter(student=student).order_by("start_date").first()
    data = {
        **_base(student),
        "issued_on": certificate.issued_on.isoformat(),
        "certificate_number": certificate.number,
        "reason": certificate.reason,
        "destination": certificate.destination,
        "admitted_on": first.start_date.isoformat() if first else "",
    }
    return _render(TC_KIND, template_key, locale, data)
