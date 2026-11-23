"""Academic structure services (Phase 6 M1; ADR-063).

Plain functions with an explicit ``actor``. Each write re-checks the permission in the
institution's scope without the cache, validates against the institution's configuration
(``capabilities``) and is audited. The database adds composite tenant/institution keys and RLS.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest
from django.utils import timezone

from apps.academics import capabilities as caps
from apps.academics.models import AcademicYear, Offering, OfferingTeacher, Subject, Term, Unit
from apps.audit.services import record
from apps.core.tenancy import require_tenant
from apps.rbac.engine import ScopeTarget, require_perm

if TYPE_CHECKING:
    from apps.identity.models import User

YEAR, STRUCTURE = "academics.year.manage", "academics.structure.manage"
SUBJECT, OFFERING = "academics.subject.manage", "academics.offering.manage"
_LOCKED_YEAR = {AcademicYear.Status.CLOSED}


def _authorise(actor: User, code: str, institution_id: Any) -> None:
    require_perm(
        actor, code, target=ScopeTarget(require_tenant().id, institution_id), use_cache=False
    )


def _audit(
    action: str, actor: User, request: HttpRequest | None, obj: Any, **metadata: Any
) -> None:
    record(
        action,
        actor=actor,
        request=request,
        target_type=f"academics.{type(obj).__name__.lower()}",
        target_id=obj.pk,
        metadata=metadata,
    )


def _clean(obj: Any) -> None:
    obj.full_clean(exclude=["tenant"], validate_unique=False, validate_constraints=False)


def _institution(institution: Any) -> Any:
    from apps.tenancy.models import Institution

    row = Institution.objects.filter(pk=getattr(institution, "pk", institution)).first()
    if row is None or row.archived_at is not None:
        raise ValidationError({"institution": "Unknown institution."})
    return row


# --------------------------------------------------------------------------- years and terms
@transaction.atomic
def create_year(
    *,
    actor: User,
    institution: Any,
    code: str,
    name: str,
    start_date: dt.date,
    end_date: dt.date,
    name_i18n: dict[str, str] | None = None,
    request: HttpRequest | None = None,
) -> AcademicYear:
    inst = _institution(institution)
    _authorise(actor, YEAR, inst.pk)
    if start_date >= end_date:
        raise ValidationError({"end_date": "The year ends after it starts."})
    years = AcademicYear.objects.select_for_update().filter(institution=inst)
    if years.filter(start_date__lt=end_date, end_date__gt=start_date).exists():
        raise ValidationError({"start_date": "Academic years of an institution can't overlap."})
    if years.filter(code=code).exists():
        raise ValidationError({"code": "This code is already used."})
    year = AcademicYear(
        institution=inst,
        code=code,
        name=name,
        name_i18n=name_i18n or {},
        start_date=start_date,
        end_date=end_date,
        created_by=actor.pk,
    )
    _clean(year)
    year.save()
    _audit("academics.year.created", actor, request, year, ref=code)
    return year


@transaction.atomic
def set_year_status(
    *, actor: User, year: AcademicYear, status: str, request: HttpRequest | None = None
) -> AcademicYear:
    """planned → active → closed. One active year per institution; a closed year stays closed."""
    year = AcademicYear.objects.select_for_update().get(pk=year.pk)
    _authorise(actor, YEAR, year.institution_id)
    allowed: dict[str, set[str]] = {
        AcademicYear.Status.PLANNED: {AcademicYear.Status.ACTIVE},
        AcademicYear.Status.ACTIVE: {AcademicYear.Status.CLOSED},
    }
    if status not in allowed.get(year.status, set()):
        raise ValidationError({"status": f"A {year.status} year can't become {status}."})
    if (
        status == AcademicYear.Status.ACTIVE
        and AcademicYear.objects.filter(
            institution_id=year.institution_id, status=AcademicYear.Status.ACTIVE
        ).exists()
    ):
        raise ValidationError({"status": "Close the active year first."})
    year.status, year.updated_by = status, actor.pk
    year.save(update_fields=["status", "updated_by", "updated_at"])
    _audit("academics.year.status_changed", actor, request, year, status=status)
    return year


@transaction.atomic
def create_term(
    *,
    actor: User,
    year: AcademicYear,
    code: str,
    name: str,
    start_date: dt.date,
    end_date: dt.date,
    kind: str = Term.Kind.TERM,
    order: int = 1,
    name_i18n: dict[str, str] | None = None,
    request: HttpRequest | None = None,
) -> Term:
    year = AcademicYear.objects.select_for_update().get(pk=year.pk)
    _authorise(actor, YEAR, year.institution_id)
    if year.status in _LOCKED_YEAR:
        raise ValidationError({"year": "A closed year can't change."})
    if not (year.start_date <= start_date < end_date <= year.end_date):
        raise ValidationError({"start_date": "A term lies inside its academic year."})
    siblings = Term.objects.filter(year=year)
    if siblings.filter(start_date__lt=end_date, end_date__gt=start_date).exists():
        raise ValidationError({"start_date": "Terms of a year can't overlap."})
    if siblings.filter(code=code).exists():
        raise ValidationError({"code": "This code is already used."})
    term = Term(
        institution_id=year.institution_id,
        year=year,
        kind=kind,
        code=code,
        name=name,
        name_i18n=name_i18n or {},
        order=order,
        start_date=start_date,
        end_date=end_date,
        created_by=actor.pk,
    )
    _clean(term)
    term.save()
    _audit("academics.term.created", actor, request, term, ref=code)
    return term


# --------------------------------------------------------------------------- units
@transaction.atomic
def create_unit(
    *,
    actor: User,
    institution: Any,
    level_key: str,
    code: str,
    name: str,
    parent: Unit | None = None,
    campus: Any = None,
    capacity: int | None = None,
    order: int = 0,
    name_i18n: dict[str, str] | None = None,
    request: HttpRequest | None = None,
) -> Unit:
    inst = _institution(institution)
    _authorise(actor, STRUCTURE, inst.pk)
    levels = caps.unit_levels(inst.pk)
    if level_key not in levels:
        raise ValidationError({"level_key": "Not a structure level of this institution."})
    expected_parent_level = levels[levels.index(level_key) - 1] if levels.index(level_key) else None
    if parent is not None:
        parent = Unit.objects.select_for_update().filter(pk=parent.pk, institution=inst).first()
        if parent is None or parent.archived_at is not None:
            raise ValidationError({"parent": "Unknown or archived parent unit."})
    if (parent.level_key if parent else None) != expected_parent_level:
        raise ValidationError(
            {"parent": "A unit sits exactly one level below its parent (top level: no parent)."}
        )
    campus_id = getattr(campus, "pk", campus)
    if parent is not None and parent.campus_id is not None:
        if campus_id not in (None, parent.campus_id):
            raise ValidationError({"campus": "A unit stays on its parent's campus."})
        campus_id = parent.campus_id
    if Unit.objects.filter(institution=inst, parent=parent, code=code).exists():
        raise ValidationError({"code": "This code is already used at this place in the tree."})
    unit = Unit(
        institution=inst,
        campus_id=campus_id,
        parent=parent,
        level_key=level_key,
        code=code,
        name=name,
        name_i18n=name_i18n or {},
        capacity=capacity,
        order=order,
        created_by=actor.pk,
    )
    _clean(unit)
    unit.save()
    _audit("academics.unit.created", actor, request, unit, ref=code, level_key=level_key)
    return unit


UNIT_FIELDS = frozenset({"name", "name_i18n", "capacity", "order", "code"})


@transaction.atomic
def update_unit(
    *, actor: User, unit: Unit, changes: dict[str, Any], request: HttpRequest | None = None
) -> Unit:
    unit = Unit.objects.select_for_update().get(pk=unit.pk)
    _authorise(actor, STRUCTURE, unit.institution_id)
    unknown = set(changes) - UNIT_FIELDS
    if unknown:
        raise ValidationError(dict.fromkeys(sorted(unknown), "This field can't be changed."))
    if "code" in changes and (
        Unit.objects.filter(
            institution_id=unit.institution_id, parent_id=unit.parent_id, code=changes["code"]
        )
        .exclude(pk=unit.pk)
        .exists()
    ):
        raise ValidationError({"code": "This code is already used at this place in the tree."})
    for field, value in changes.items():
        setattr(unit, field, value)
    unit.updated_by = actor.pk
    _clean(unit)
    unit.save()
    _audit("academics.unit.updated", actor, request, unit, fields=",".join(sorted(changes)))
    return unit


@transaction.atomic
def archive_unit(*, actor: User, unit: Unit, request: HttpRequest | None = None) -> Unit:
    unit = Unit.objects.select_for_update().get(pk=unit.pk)
    _authorise(actor, STRUCTURE, unit.institution_id)
    if Unit.objects.filter(parent=unit, archived_at__isnull=True).exists():
        raise ValidationError({"unit": "Archive its units first."})
    open_years = ~Q(year__status=AcademicYear.Status.CLOSED)
    if Offering.objects.filter(open_years, unit=unit).exists():
        raise ValidationError({"unit": "The unit has offerings in an open year."})
    unit.archived_at, unit.updated_by = timezone.now(), actor.pk
    unit.save(update_fields=["archived_at", "updated_by", "updated_at"])
    _audit("academics.unit.archived", actor, request, unit, ref=unit.code)
    return unit


# --------------------------------------------------------------------------- subjects
def _credits(institution_id: Any, credits: Decimal | None, *, field: str = "credits") -> None:
    if caps.capability(institution_id, caps.CREDIT_BASED):
        if credits is None:
            raise ValidationError({field: "Credits are required (credit-based institution)."})
    elif credits is not None:
        raise ValidationError({field: "This institution does not use credits."})


@transaction.atomic
def create_subject(
    *,
    actor: User,
    institution: Any,
    code: str,
    name: str,
    subject_type: str = "core",
    credits: Decimal | None = None,
    name_i18n: dict[str, str] | None = None,
    request: HttpRequest | None = None,
) -> Subject:
    inst = _institution(institution)
    _authorise(actor, SUBJECT, inst.pk)
    _credits(inst.pk, credits)
    if Subject.objects.filter(institution=inst, code=code).exists():
        raise ValidationError({"code": "This code is already used."})
    subject = Subject(
        institution=inst,
        code=code,
        name=name,
        name_i18n=name_i18n or {},
        subject_type=subject_type,
        credits=credits,
        created_by=actor.pk,
    )
    _clean(subject)
    subject.save()
    _audit("academics.subject.created", actor, request, subject, ref=code)
    return subject


@transaction.atomic
def archive_subject(
    *, actor: User, subject: Subject, request: HttpRequest | None = None
) -> Subject:
    subject = Subject.objects.select_for_update().get(pk=subject.pk)
    _authorise(actor, SUBJECT, subject.institution_id)
    if Offering.objects.filter(
        ~Q(year__status=AcademicYear.Status.CLOSED), subject=subject
    ).exists():
        raise ValidationError({"subject": "The subject has offerings in an open year."})
    subject.archived_at, subject.updated_by = timezone.now(), actor.pk
    subject.save(update_fields=["archived_at", "updated_by", "updated_at"])
    _audit("academics.subject.archived", actor, request, subject, ref=subject.code)
    return subject


# --------------------------------------------------------------------------- offerings
@transaction.atomic
def create_offering(
    *,
    actor: User,
    year: AcademicYear,
    unit: Unit,
    subject: Subject,
    term: Term | None = None,
    credits: Decimal | None = None,
    request: HttpRequest | None = None,
) -> Offering:
    year = AcademicYear.objects.get(pk=year.pk)
    _authorise(actor, OFFERING, year.institution_id)
    if year.status in _LOCKED_YEAR:
        raise ValidationError({"year": "A closed year can't change."})
    unit = Unit.objects.get(pk=unit.pk)
    subject = Subject.objects.get(pk=subject.pk)
    if {unit.institution_id, subject.institution_id} != {year.institution_id}:
        raise ValidationError({"unit": "Year, unit and subject belong to one institution."})
    if unit.archived_at or subject.archived_at:
        raise ValidationError({"unit": "Archived units and subjects take no new offerings."})
    if term is not None and term.year_id != year.pk:
        raise ValidationError({"term": "The term belongs to another year."})
    if term is None and caps.capability(year.institution_id, caps.SEMESTER_BASED):
        raise ValidationError({"term": "A term is required (semester-based institution)."})
    if credits is not None:
        _credits(year.institution_id, credits)
    if Offering.objects.filter(year=year, term=term, unit=unit, subject=subject).exists():
        raise ValidationError({"subject": "This subject is already offered here."})
    offering = Offering(
        institution_id=year.institution_id,
        year=year,
        term=term,
        unit=unit,
        subject=subject,
        credits=credits,
        created_by=actor.pk,
    )
    offering.save()
    _audit("academics.offering.created", actor, request, offering, subject=subject.code)
    return offering


@transaction.atomic
def assign_teacher(
    *,
    actor: User,
    offering: Offering,
    membership: Any,
    role: str = OfferingTeacher.Role.PRIMARY,
    request: HttpRequest | None = None,
) -> OfferingTeacher:
    from apps.tenancy.models import Membership

    offering = Offering.objects.get(pk=offering.pk)
    _authorise(actor, OFFERING, offering.institution_id)
    member = Membership.objects.filter(pk=getattr(membership, "pk", membership)).first()
    if member is None or member.status != Membership.Status.ACTIVE:
        raise ValidationError({"membership": "Teachers are active members."})
    if role not in OfferingTeacher.Role.values:
        raise ValidationError({"role": "Unknown teaching role."})
    if OfferingTeacher.objects.filter(offering=offering, membership=member).exists():
        raise ValidationError({"membership": "Already assigned to this offering."})
    row = OfferingTeacher.objects.create(
        offering=offering, membership=member, role=role, created_by=actor.pk
    )
    _audit("academics.offering.teacher_assigned", actor, request, offering, role=role)
    return row


@transaction.atomic
def remove_teacher(
    *, actor: User, assignment: OfferingTeacher, request: HttpRequest | None = None
) -> None:
    assignment = OfferingTeacher.objects.get(pk=assignment.pk)
    offering = Offering.objects.get(pk=assignment.offering_id)
    _authorise(actor, OFFERING, offering.institution_id)
    assignment.delete()
    _audit("academics.offering.teacher_removed", actor, request, offering)
