"""Staff services: departments, designations, profiles and class-teacher advisors (Phase 7 M3;
ADR-070).

Plain functions with an explicit ``actor``. Each write re-checks its permission in the
institution's scope without the cache, validates and is audited. Personal data (names, phones,
emails) never goes into audit metadata.

* Departments and designations need ``staff.structure.manage``; profiles need
  ``staff.profile.manage``.
* Staff numbers come from the Studio numbering sequence ``staff`` when the tenant defined it;
  otherwise staff give the number (as for students, ADR-074 Q1).
* A profile may have no login (support staff). Linking a login needs an active membership of
  the tenant, at most one profile per login and institution.
* Advisors (class teachers) are assigned with ``academics.offering.manage``: the same authority
  that assigns subject teachers to offerings (ADR-063). Advising needs a login, because the
  advisor sees the unit's students through it.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.audit.services import record
from apps.core.people import validate_person
from apps.core.tenancy import require_tenant
from apps.rbac.engine import ScopeTarget, require_perm
from apps.staff.models import Department, Designation, StaffProfile, UnitAdvisor

if TYPE_CHECKING:
    from apps.identity.models import User

MANAGE, STRUCTURE = "staff.profile.manage", "staff.structure.manage"
ADVISORS = "academics.offering.manage"
ENTITY = "staff.profile"
NUMBER_SEQUENCE = "staff"
PROFILE_FIELDS = frozenset({"name", "name_i18n", "gender", "email", "phone", "joining_date"})
_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
_NUMBER = re.compile(r"^[\w./-]{1,64}$")


def target_of(institution_id: Any) -> ScopeTarget:
    return ScopeTarget(require_tenant().id, institution_id)


def _authorise(actor: User, code: str, institution_id: Any) -> None:
    require_perm(actor, code, target=target_of(institution_id), use_cache=False)


def _audit(action: str, actor: Any, request: HttpRequest | None, obj: Any, **metadata: Any) -> None:
    record(
        action,
        actor=actor,
        request=request,
        target_type=f"staff.{type(obj).__name__.lower()}",
        target_id=obj.pk,
        metadata=metadata,
    )


def _institution(institution: Any) -> Any:
    from apps.tenancy.models import Institution

    row = Institution.objects.filter(pk=getattr(institution, "pk", institution)).first()
    if row is None:
        raise ValidationError({"institution": "Unknown institution."})
    return row


def _in_institution(model: Any, value: Any, institution_id: Any, field: str) -> Any:
    """A live row of ``model`` in the institution, ``None`` for an empty value."""
    if value in (None, ""):
        return None
    row = model.objects.filter(
        pk=getattr(value, "pk", value), institution_id=institution_id
    ).first()
    if row is None or getattr(row, "archived_at", None) is not None:
        raise ValidationError({field: "Choose one of this institution."})
    return row


def _labels(name: Any, name_i18n: Any) -> tuple[str, dict[str, str]]:
    text = str(name or "").strip()
    if not text or len(text) > 120:
        raise ValidationError({"name": "Give a name of at most 120 characters."})
    labels = name_i18n or {}
    if not isinstance(labels, dict) or not all(
        isinstance(k, str) and isinstance(v, str) and len(v) <= 120 for k, v in labels.items()
    ):
        raise ValidationError({"name_i18n": "Names per language are text."})
    return text, labels


def _code(code: Any) -> str:
    text = str(code or "").strip()
    if not _CODE.match(text):
        raise ValidationError(
            {"code": "Use 1-32 letters, digits and . - _ (starting alphanumeric)."}
        )
    return text


# --------------------------------------------------------------------------- structure
@transaction.atomic
def create_department(
    *,
    actor: User,
    institution: Any,
    code: str,
    name: str,
    name_i18n: dict[str, str] | None = None,
    kind: str = Department.Kind.ACADEMIC,
    parent: Any = None,
    request: HttpRequest | None = None,
) -> Department:
    inst = _institution(institution)
    _authorise(actor, STRUCTURE, inst.pk)
    code = _code(code)
    text, labels = _labels(name, name_i18n)
    if kind not in Department.Kind.values:
        raise ValidationError({"kind": "Choose academic or administrative."})
    if Department.objects.filter(institution=inst, code=code).exists():
        raise ValidationError({"code": "This code is already used."})
    row = Department.objects.create(
        institution=inst, code=code, name=text, name_i18n=labels, kind=kind,
        parent=_in_institution(Department, parent, inst.pk, "parent"), created_by=actor.pk,
    )  # fmt: skip
    _audit("staff.department.created", actor, request, row, ref=code)
    return row


@transaction.atomic
def update_department(
    *,
    actor: User,
    department: Department,
    changes: dict[str, Any],
    request: HttpRequest | None = None,
) -> Department:
    """``changes`` may hold ``name``, ``name_i18n``, ``kind``, ``parent`` and ``archived``."""
    row = Department.objects.select_for_update().get(pk=department.pk)
    _authorise(actor, STRUCTURE, row.institution_id)
    if "name" in changes or "name_i18n" in changes:
        row.name, row.name_i18n = _labels(
            changes.get("name", row.name), changes.get("name_i18n", row.name_i18n)
        )
    if "kind" in changes:
        if changes["kind"] not in Department.Kind.values:
            raise ValidationError({"kind": "Choose academic or administrative."})
        row.kind = changes["kind"]
    if "parent" in changes:
        parent = _in_institution(Department, changes["parent"], row.institution_id, "parent")
        seen = parent
        while seen is not None:  # a department never sits below itself
            if seen.pk == row.pk:
                raise ValidationError({"parent": "A department can't sit below itself."})
            seen = Department.objects.filter(pk=seen.parent_id).first()
        row.parent = parent
    if "archived" in changes:
        if changes["archived"] and row.archived_at is None:
            if (
                StaffProfile.objects.filter(department=row)
                .exclude(status=StaffProfile.Status.LEFT)
                .exists()
            ):
                raise ValidationError({"archived": "Move the department's staff first."})
            row.archived_at = timezone.now()
        elif not changes["archived"]:
            row.archived_at = None
    row.updated_by = actor.pk
    row.save()
    _audit("staff.department.updated", actor, request, row, fields=",".join(sorted(changes)))
    return row


@transaction.atomic
def create_designation(
    *,
    actor: User,
    institution: Any,
    code: str,
    name: str,
    name_i18n: dict[str, str] | None = None,
    request: HttpRequest | None = None,
) -> Designation:
    inst = _institution(institution)
    _authorise(actor, STRUCTURE, inst.pk)
    code = _code(code)
    text, labels = _labels(name, name_i18n)
    if Designation.objects.filter(institution=inst, code=code).exists():
        raise ValidationError({"code": "This code is already used."})
    row = Designation.objects.create(
        institution=inst, code=code, name=text, name_i18n=labels, created_by=actor.pk
    )
    _audit("staff.designation.created", actor, request, row, ref=code)
    return row


@transaction.atomic
def update_designation(
    *,
    actor: User,
    designation: Designation,
    changes: dict[str, Any],
    request: HttpRequest | None = None,
) -> Designation:
    """``changes`` may hold ``name``, ``name_i18n`` and ``archived``."""
    row = Designation.objects.select_for_update().get(pk=designation.pk)
    _authorise(actor, STRUCTURE, row.institution_id)
    if "name" in changes or "name_i18n" in changes:
        row.name, row.name_i18n = _labels(
            changes.get("name", row.name), changes.get("name_i18n", row.name_i18n)
        )
    if "archived" in changes:
        row.archived_at = (row.archived_at or timezone.now()) if changes["archived"] else None
    row.updated_by = actor.pk
    row.save()
    _audit("staff.designation.updated", actor, request, row, fields=",".join(sorted(changes)))
    return row


# --------------------------------------------------------------------------- profiles
def _membership(value: Any, institution_id: Any, profile_id: Any = None) -> Any:
    from apps.tenancy.models import Membership

    if value in (None, ""):
        return None
    member = Membership.objects.filter(pk=getattr(value, "pk", value)).first()
    if member is None or member.status != Membership.Status.ACTIVE:
        raise ValidationError({"membership": "Choose an active member of the organisation."})
    taken = StaffProfile.objects.filter(institution_id=institution_id, membership=member)
    if taken.exclude(pk=profile_id).exists():
        raise ValidationError({"membership": "This login already has a profile here."})
    return member


def _campus(value: Any, institution_id: Any) -> Any:
    from apps.tenancy.models import Campus

    return _in_institution(Campus, value, institution_id, "campus")


def _choice(value: Any, choices: Any, field: str) -> str:
    if value not in choices.values:
        raise ValidationError({field: "Choose a value from the list."})
    return str(value)


def _next_number(institution: Any) -> str:
    from apps.customization import numbering
    from apps.customization.models import NumberingSequence

    if not NumberingSequence.objects.filter(key=NUMBER_SEQUENCE, archived_at__isnull=True).exists():
        raise ValidationError(
            {"number": "Give a staff number, or define the 'staff' numbering sequence."}
        )
    return numbering.allocate(NUMBER_SEQUENCE, institution=institution)


@transaction.atomic
def create_profile(
    *,
    actor: User,
    institution: Any,
    values: dict[str, Any],
    extra: dict[str, Any] | None = None,
    number: str = "",
    campus: Any = None,
    department: Any = None,
    designation: Any = None,
    membership: Any = None,
    employment_type: str = StaffProfile.Employment.PERMANENT,
    request: HttpRequest | None = None,
) -> StaffProfile:
    from apps.customization.fields import validate_values

    inst = _institution(institution)
    _authorise(actor, MANAGE, inst.pk)
    core = validate_person(values, PROFILE_FIELDS)
    if not core.get("name"):
        raise ValidationError({"name": "The staff member's name is required."})
    custom = validate_values(ENTITY, extra or {})
    number = number.strip()
    if number and not _NUMBER.match(number):
        raise ValidationError({"number": "Use letters, digits and . / - _ (at most 64)."})
    if number and StaffProfile.objects.filter(institution=inst, number=number).exists():
        raise ValidationError({"number": "This number is already used."})
    row = StaffProfile.objects.create(
        institution=inst,
        campus=_campus(campus, inst.pk),
        department=_in_institution(Department, department, inst.pk, "department"),
        designation=_in_institution(Designation, designation, inst.pk, "designation"),
        membership=_membership(membership, inst.pk),
        employment_type=_choice(employment_type, StaffProfile.Employment, "employment_type"),
        number=number or _next_number(inst),
        extra=custom,
        created_by=actor.pk,
        **core,
    )
    _audit("staff.profile.created", actor, request, row, ref=row.number,
           login=row.membership_id is not None)  # fmt: skip
    return row


@transaction.atomic
def update_profile(
    *,
    actor: User,
    profile: StaffProfile,
    values: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
    links: dict[str, Any] | None = None,
    request: HttpRequest | None = None,
) -> StaffProfile:
    """``links`` may hold ``campus``, ``department``, ``designation``, ``membership``,
    ``status`` and ``employment_type`` (``None`` clears a link)."""
    from apps.customization.fields import merge_for_update

    row = StaffProfile.objects.select_for_update().get(pk=profile.pk)
    _authorise(actor, MANAGE, row.institution_id)
    core = validate_person(values or {}, PROFILE_FIELDS)
    if "name" in core and not core["name"]:
        raise ValidationError({"name": "The staff member's name is required."})
    for key, value in core.items():
        setattr(row, key, value)
    links = links or {}
    inst = row.institution_id
    if "campus" in links:
        row.campus = _campus(links["campus"], inst)
    if "department" in links:
        row.department = _in_institution(Department, links["department"], inst, "department")
    if "designation" in links:
        row.designation = _in_institution(Designation, links["designation"], inst, "designation")
    if "membership" in links:
        row.membership = _membership(links["membership"], inst, row.pk)
    if "status" in links:
        row.status = _choice(links["status"], StaffProfile.Status, "status")
    if "employment_type" in links:
        row.employment_type = _choice(
            links["employment_type"], StaffProfile.Employment, "employment_type"
        )
    if extra is not None:
        row.extra = merge_for_update(ENTITY, row.extra, extra, actor, target_of(inst))
    if row.status != StaffProfile.Status.ACTIVE or row.membership_id is None:
        # Advising needs an active profile with a login: end the current assignments.
        _end_advising(row)
    row.updated_by = actor.pk
    row.save()
    changed = [*core, *links, *(["extra"] if extra else [])]
    _audit("staff.profile.updated", actor, request, row, fields=",".join(sorted(changed)))
    return row


def _end_advising(profile: StaffProfile) -> None:
    from apps.academics.models import AcademicYear

    UnitAdvisor.objects.filter(staff=profile).exclude(
        year__status=AcademicYear.Status.CLOSED
    ).delete()


# --------------------------------------------------------------------------- advisors
@transaction.atomic
def assign_advisor(
    *,
    actor: User,
    year: Any,
    unit: Any,
    staff: StaffProfile,
    is_primary: bool = True,
    request: HttpRequest | None = None,
) -> UnitAdvisor:
    """Make ``staff`` a class teacher (advisor) of ``unit`` for ``year``. A primary advisor
    replaces the unit's current primary (who stays as an assistant)."""
    from apps.academics.models import AcademicYear, Unit

    staff = StaffProfile.objects.select_for_update().get(pk=staff.pk)
    inst = staff.institution_id
    _authorise(actor, ADVISORS, inst)
    year_row = AcademicYear.objects.filter(
        pk=getattr(year, "pk", year), institution_id=inst
    ).first()
    if year_row is None or year_row.status == AcademicYear.Status.CLOSED:
        raise ValidationError({"year": "Choose an open academic year of this institution."})
    unit_row = _in_institution(Unit, unit, inst, "unit")
    if unit_row is None:
        raise ValidationError({"unit": "Choose a unit of this institution."})
    if staff.status != StaffProfile.Status.ACTIVE or staff.membership_id is None:
        raise ValidationError({"staff": "Advisors are active staff with a login."})
    _membership_is_active(staff.membership_id)
    if UnitAdvisor.objects.filter(year=year_row, unit=unit_row, staff=staff).exists():
        raise ValidationError({"staff": "Already an advisor of this unit."})
    if is_primary:
        UnitAdvisor.objects.filter(year=year_row, unit=unit_row, is_primary=True).update(
            is_primary=False
        )
    row = UnitAdvisor.objects.create(
        institution_id=inst, year=year_row, unit=unit_row, staff=staff, is_primary=is_primary,
        created_by=actor.pk,
    )  # fmt: skip
    _audit("staff.advisor.assigned", actor, request, row, primary=is_primary)
    return row


def _membership_is_active(membership_id: Any) -> None:
    from apps.tenancy.models import Membership

    if not Membership.objects.filter(pk=membership_id, status=Membership.Status.ACTIVE).exists():
        raise ValidationError({"staff": "Advisors are active staff with a login."})


@transaction.atomic
def remove_advisor(
    *, actor: User, advisor: UnitAdvisor, request: HttpRequest | None = None
) -> None:
    row = UnitAdvisor.objects.select_for_update().get(pk=advisor.pk)
    _authorise(actor, ADVISORS, row.institution_id)
    staff = StaffProfile.objects.get(pk=row.staff_id)
    row.delete()
    _audit("staff.advisor.removed", actor, request, staff)
