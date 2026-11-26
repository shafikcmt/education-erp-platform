"""Student, guardian and enrollment services (Phase 7 M1; ADR-068, ADR-074).

Plain functions with an explicit ``actor``. Each write re-checks its permission in the
institution's scope without the cache, validates (custom fields against the Studio definitions,
leaf units, open years) and is audited. Personal data (names, phones, emails) never goes into
audit metadata.

* Student numbers come from the Studio numbering sequence ``student`` when the tenant defined it
  (ADR-074 Q1); otherwise staff give the number.
* Guardians are matched by email or phone **within the tenant only** before a new one is created,
  and duplicates can be merged by staff (ADR-074 Q8).
* An enrollment puts a student in a leaf unit of an open year of the same institution; at most
  one active enrollment per student and year (also a database constraint).
"""

from __future__ import annotations

import datetime as dt
import re
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpRequest

from apps.audit.services import record
from apps.core.people import normalise_phone
from apps.core.people import validate_person as _person
from apps.core.tenancy import require_tenant
from apps.rbac.engine import ScopeTarget, require_perm
from apps.students.models import Enrollment, Guardian, Student, StudentGuardian

if TYPE_CHECKING:
    from apps.identity.models import User

MANAGE, GUARDIANS = "students.student.manage", "students.guardian.manage"
STUDENT_ENTITY, GUARDIAN_ENTITY = "students.student", "students.guardian"
NUMBER_SEQUENCE = "student"
STUDENT_FIELDS = frozenset({"name", "name_i18n", "date_of_birth", "gender", "email", "phone"})
GUARDIAN_FIELDS = frozenset({"name", "name_i18n", "phone", "email"})
RELATIONS = frozenset({"father", "mother", "guardian", "sibling", "grandparent", "relative",
                       "other"})  # fmt: skip


def target_of(institution_id: Any) -> ScopeTarget:
    return ScopeTarget(require_tenant().id, institution_id)


def _authorise(actor: User, code: str, institution_id: Any) -> None:
    require_perm(actor, code, target=target_of(institution_id), use_cache=False)


def require_manage(actor: User, institution_id: Any) -> None:
    _authorise(actor, MANAGE, institution_id)


def _audit(action: str, actor: Any, request: HttpRequest | None, obj: Any, **metadata: Any) -> None:
    record(
        action,
        actor=actor,
        request=request,
        target_type=f"students.{type(obj).__name__.lower()}",
        target_id=obj.pk,
        metadata=metadata,
    )


def _institution(institution: Any) -> Any:
    from apps.tenancy.models import Institution

    row = Institution.objects.filter(pk=getattr(institution, "pk", institution)).first()
    if row is None:
        raise ValidationError({"institution": "Unknown institution."})
    return row


def active_students() -> int:
    return Student.objects.filter(status=Student.Status.ACTIVE).count()


def _check_student_limit() -> None:
    from apps.customization.quotas import limit

    cap = limit("max_active_students")
    if cap and active_students() >= cap:
        raise ValidationError(
            {"quota": f"Your plan allows {cap} active students. Upgrade to add more."}
        )


def _next_number(institution: Any) -> str:
    from apps.customization import numbering
    from apps.customization.models import NumberingSequence

    if not NumberingSequence.objects.filter(key=NUMBER_SEQUENCE, archived_at__isnull=True).exists():
        raise ValidationError(
            {"number": "Give a student number, or define the 'student' numbering sequence."}
        )
    return numbering.allocate(NUMBER_SEQUENCE, institution=institution)


# --------------------------------------------------------------------------- students
@transaction.atomic
def create_student(
    *,
    actor: User,
    institution: Any,
    values: dict[str, Any],
    extra: dict[str, Any] | None = None,
    number: str = "",
    source_application_id: Any = None,
    request: HttpRequest | None = None,
) -> Student:
    from apps.customization.fields import validate_values

    inst = _institution(institution)
    _authorise(actor, MANAGE, inst.pk)
    core = _person(values, STUDENT_FIELDS)
    if not core.get("name"):
        raise ValidationError({"name": "The student's name is required."})
    custom = validate_values(STUDENT_ENTITY, extra or {})
    student = insert_student(
        institution=inst, core=core, custom=custom, number=number,
        source_application_id=source_application_id, created_by=actor.pk,
    )  # fmt: skip
    _audit("students.student.created", actor, request, student, ref=student.number)
    return student


def insert_student(
    *,
    institution: Any,
    core: dict[str, Any],
    custom: dict[str, Any],
    number: str = "",
    source_application_id: Any = None,
    created_by: Any = None,
) -> Student:
    """Insert a validated student (no permission check: callers authorise; the conversion of an
    accepted application is authorised by the admission decision)."""
    _check_student_limit()
    number = number.strip()
    if number and (len(number) > 64 or not re.match(r"^[\w./-]+$", number)):
        raise ValidationError({"number": "Use letters, digits and . / - _ (at most 64)."})
    if number and Student.objects.filter(institution=institution, number=number).exists():
        raise ValidationError({"number": "This number is already used."})
    return Student.objects.create(
        institution=institution,
        number=number or _next_number(institution),
        extra=custom,
        source_application_id=source_application_id,
        created_by=created_by,
        **core,
    )


@transaction.atomic
def update_student(
    *,
    actor: User,
    student: Student,
    values: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
    request: HttpRequest | None = None,
) -> Student:
    from apps.customization.fields import merge_for_update

    student = Student.objects.select_for_update().get(pk=student.pk)
    _authorise(actor, MANAGE, student.institution_id)
    core = _person(values or {}, STUDENT_FIELDS)
    if "name" in core and not core["name"]:
        raise ValidationError({"name": "The student's name is required."})
    for key, value in core.items():
        setattr(student, key, value)
    if extra is not None:
        student.extra = merge_for_update(
            STUDENT_ENTITY, student.extra, extra, actor, target_of(student.institution_id)
        )
    student.updated_by = actor.pk
    student.save()
    _audit("students.student.updated", actor, request, student,
           fields=",".join(sorted([*core, *(["extra"] if extra else [])])))  # fmt: skip
    return student


# --------------------------------------------------------------------------- guardians
def match_guardian(*, phone: str = "", email: str = "") -> Guardian | None:
    """The tenant's guardian with this email or phone, if any (never across tenants: RLS and the
    tenant manager both scope the query)."""
    query = Q()
    if email:
        query |= Q(email=email.strip().lower())
    if phone:
        query |= Q(phone=normalise_phone(phone))
    if not query:
        return None
    return Guardian.objects.filter(query).order_by("created_at").first()


@transaction.atomic
def link_guardian(
    *,
    actor: User,
    student: Student,
    values: dict[str, Any] | None = None,
    guardian: Guardian | None = None,
    extra: dict[str, Any] | None = None,
    relation: str = "guardian",
    is_primary: bool = False,
    can_pickup: bool = True,
    receives_notices: bool = True,
    request: HttpRequest | None = None,
) -> StudentGuardian:
    """Link an existing guardian, or the tenant's guardian with the same email or phone, or a new
    one created from ``values``."""
    from apps.customization.fields import validate_values

    student = Student.objects.select_for_update().get(pk=student.pk)
    _authorise(actor, GUARDIANS, student.institution_id)
    if relation not in RELATIONS:
        raise ValidationError({"relation": "Choose a relation from the list."})
    if guardian is None:
        core = _person(values or {}, GUARDIAN_FIELDS)
        guardian, created = find_or_create_guardian(
            core, validate_values(GUARDIAN_ENTITY, extra or {}), created_by=actor.pk
        )
        if created:
            _audit("students.guardian.created", actor, request, guardian)
    link = attach_guardian(
        student, guardian, relation=relation, is_primary=is_primary, can_pickup=can_pickup,
        receives_notices=receives_notices, created_by=actor.pk,
    )  # fmt: skip
    _audit("students.guardian.linked", actor, request, student, relation=relation)
    return link


def find_or_create_guardian(
    core: dict[str, Any], custom: dict[str, Any], *, created_by: Any = None
) -> tuple[Guardian, bool]:
    """The tenant's guardian with the same email or phone, or a new one (validated values)."""
    if not core.get("phone") and not core.get("email"):
        raise ValidationError({"phone": "A phone number or an email address is needed."})
    guardian = match_guardian(phone=core.get("phone", ""), email=core.get("email", ""))
    if guardian is not None:
        return guardian, False
    if not core.get("name"):
        raise ValidationError({"name": "The guardian's name is required."})
    return Guardian.objects.create(extra=custom, created_by=created_by, **core), True


def attach_guardian(
    student: Student,
    guardian: Guardian,
    *,
    relation: str,
    is_primary: bool = False,
    can_pickup: bool = True,
    receives_notices: bool = True,
    created_by: Any = None,
) -> StudentGuardian:
    """Link (no permission check: callers authorise). One primary guardian per student."""
    if StudentGuardian.objects.filter(student=student, guardian=guardian).exists():
        raise ValidationError({"guardian": "This guardian is already linked."})
    if is_primary:
        StudentGuardian.objects.filter(student=student, is_primary=True).update(is_primary=False)
    return StudentGuardian.objects.create(
        student=student, guardian=guardian, relation=relation, is_primary=is_primary,
        can_pickup=can_pickup, receives_notices=receives_notices, created_by=created_by,
    )  # fmt: skip


@transaction.atomic
def unlink_guardian(
    *, actor: User, link: StudentGuardian, request: HttpRequest | None = None
) -> None:
    link = StudentGuardian.objects.select_for_update().get(pk=link.pk)
    student = Student.objects.get(pk=link.student_id)
    _authorise(actor, GUARDIANS, student.institution_id)
    link.delete()
    _audit("students.guardian.unlinked", actor, request, student)


@transaction.atomic
def merge_guardians(
    *, actor: User, keep: Guardian, duplicate: Guardian, request: HttpRequest | None = None
) -> Guardian:
    """Move the duplicate's links to ``keep`` and delete the duplicate. The actor needs
    ``students.guardian.manage`` in the institution of every student either guardian has."""
    if keep.pk == duplicate.pk:
        raise ValidationError({"duplicate": "Choose two different guardians."})
    keep = Guardian.objects.select_for_update().get(pk=keep.pk)
    duplicate = Guardian.objects.select_for_update().get(pk=duplicate.pk)
    links = StudentGuardian.objects.filter(guardian__in=[keep, duplicate])
    institutions = set(
        Student.objects.filter(pk__in=links.values("student_id")).values_list(
            "institution_id", flat=True
        )
    )
    for institution_id in institutions:
        _authorise(actor, GUARDIANS, institution_id)
    if keep.membership_id and duplicate.membership_id:
        raise ValidationError({"duplicate": "Both guardians have a login; unlink one first."})
    kept_students = set(
        StudentGuardian.objects.filter(guardian=keep).values_list("student_id", flat=True)
    )
    for link in StudentGuardian.objects.filter(guardian=duplicate):
        if link.student_id in kept_students:
            link.delete()  # the student already has the kept guardian
        else:
            link.guardian = keep
            link.save(update_fields=["guardian", "updated_at"])
    for field in ("phone", "email"):
        if not getattr(keep, field) and getattr(duplicate, field):
            setattr(keep, field, getattr(duplicate, field))
    if duplicate.membership_id and not keep.membership_id:
        keep.membership_id, duplicate.membership_id = duplicate.membership_id, None
        duplicate.save(update_fields=["membership", "updated_at"])
    keep.extra = {**duplicate.extra, **keep.extra}
    keep.updated_by = actor.pk
    keep.save()
    duplicate.delete()
    _audit("students.guardian.merged", actor, request, keep)
    return keep


# --------------------------------------------------------------------------- enrollments
def _leaf_unit(unit: Any, institution_id: Any) -> Any:
    from apps.academics.models import Unit

    row = Unit.objects.filter(
        pk=getattr(unit, "pk", unit), institution_id=institution_id, archived_at__isnull=True
    ).first()
    if row is None:
        raise ValidationError({"unit": "Choose a unit of this institution."})
    if Unit.objects.filter(parent=row, archived_at__isnull=True).exists():
        raise ValidationError(
            {"unit": "Choose the unit the student sits in (one without units below it)."}
        )
    return row


def _open_year(year: Any, institution_id: Any) -> Any:
    from apps.academics.models import AcademicYear

    row = AcademicYear.objects.filter(
        pk=getattr(year, "pk", year), institution_id=institution_id
    ).first()
    if row is None or row.status == AcademicYear.Status.CLOSED:
        raise ValidationError({"year": "Choose an open academic year of this institution."})
    return row


@transaction.atomic
def enroll(
    *,
    actor: User,
    student: Student,
    year: Any,
    unit: Any,
    roll_number: str = "",
    start_date: dt.date | None = None,
    request: HttpRequest | None = None,
) -> Enrollment:
    student = Student.objects.select_for_update().get(pk=student.pk)
    _authorise(actor, MANAGE, student.institution_id)
    row = insert_enrollment(
        student, year=year, unit=unit, roll_number=roll_number, start_date=start_date,
        created_by=actor.pk,
    )  # fmt: skip
    _audit("students.enrollment.created", actor, request, row)
    return row


def insert_enrollment(
    student: Student,
    *,
    year: Any,
    unit: Any,
    roll_number: str = "",
    start_date: dt.date | None = None,
    created_by: Any = None,
) -> Enrollment:
    """Validate and insert an enrollment of a locked student (no permission check: callers
    authorise)."""
    if student.status != Student.Status.ACTIVE:
        raise ValidationError({"student": "Only active students are enrolled."})
    year_row = _open_year(year, student.institution_id)
    unit_row = _leaf_unit(unit, student.institution_id)
    roll_number = roll_number.strip()
    if len(roll_number) > 16:
        raise ValidationError({"roll_number": "At most 16 characters."})
    if Enrollment.objects.filter(
        student=student, year=year_row, status=Enrollment.Status.ACTIVE
    ).exists():
        raise ValidationError({"year": "The student is already enrolled for this year."})
    start = start_date or max(dt.date.today(), year_row.start_date)
    if start < year_row.start_date or start > year_row.end_date:
        raise ValidationError({"start_date": "The start date is within the academic year."})
    try:
        with transaction.atomic():
            row = Enrollment.objects.create(
                institution_id=student.institution_id, student=student, year=year_row,
                unit=unit_row, roll_number=roll_number, start_date=start, created_by=created_by,
            )  # fmt: skip
    except IntegrityError:
        raise ValidationError(
            {"roll_number": "This roll number is already used in the unit."}
        ) from None
    return row
