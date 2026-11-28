"""Leave requests (Phase 8 M3; plan §6, ADR-081 Q7).

* **Who may request:** a guardian for their child, a student for themselves, a staff member for
  themselves (each with ``attendance.leave.request``), or a reviewer of that person on their
  behalf.
* **Who may review:** ``attendance.leave.review`` in the person's institution, and
  - for a student: ``attendance.record.manage`` at the institution or the student's campus, or
    being the class teacher (advisor) of the student's current unit;
  - for a staff member: ``staff.profile.view`` at the institution or the staff member's campus.
* **Approval:** if the institution names a published workflow (``attendance.leave_workflow``),
  it starts with the request and must finish before the decision; otherwise the decision is the
  single built-in step. Approved leave is pre-filled in registers (``selectors.roster``) and never
  overwrites a saved status.
* Overlapping pending or approved leave for the same person is refused. Reasons and notes are
  never written to the audit log.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.http import HttpRequest
from django.utils import timezone

from apps.attendance import selectors
from apps.attendance.config import config_for
from apps.attendance.models import LeaveRequest
from apps.audit.services import record as audit
from apps.core.tenancy import require_tenant
from apps.rbac.engine import ScopeTarget

if TYPE_CHECKING:
    from apps.identity.models import User

REQUEST, REVIEW = "attendance.leave.request", "attendance.leave.review"
STAFF_VIEW, STAFF_OWN = "staff.profile.view", "staff.profile.view_own"
MAX_DAYS, MAX_PAST_DAYS = 60, 30
OPEN = (LeaveRequest.State.PENDING, LeaveRequest.State.APPROVED)


def _audit(action: str, actor: Any, request: HttpRequest | None, row: LeaveRequest, **meta: Any):  # type: ignore[no-untyped-def]
    audit(action, actor=actor, request=request, target_type="attendance.leaverequest",
          target_id=row.pk, metadata=meta)  # fmt: skip


def _mine(actor: Any) -> list[Any]:
    from apps.students.selectors import memberships

    return memberships(actor)


def _holds_anywhere(actor: Any, code: str) -> bool:
    from apps.students.selectors import holds_anywhere

    return holds_anywhere(actor, code)


# --------------------------------------------------------------------------- who may review
def _reviews_student(actor: Any, student: Any) -> bool:
    from apps.students.selectors import current_units, holds_in_institution

    inst = student.institution_id
    if not holds_in_institution(actor, REVIEW, inst):
        return False
    unit, campus = current_units([student.pk]).get(student.pk, (None, None))
    if selectors.holds_at(actor, selectors.MANAGE, inst, campus):
        return True
    return unit is not None and unit in selectors.advised_units(actor, inst)


def _reviews_staff(actor: Any, profile: Any) -> bool:
    from apps.students.selectors import holds_in_institution

    inst = profile.institution_id
    return holds_in_institution(actor, REVIEW, inst) and selectors.holds_at(
        actor, STAFF_VIEW, inst, profile.campus_id
    )


def can_review(actor: Any, leave: LeaveRequest) -> bool:
    if leave.student_id is not None:
        return _reviews_student(actor, leave.student)
    return _reviews_staff(actor, leave.staff)


def _may_request_for_student(actor: Any, student: Any) -> bool:
    from apps.students.selectors import relation_to

    if relation_to(actor, student.pk) and _holds_anywhere(actor, REQUEST):
        return True
    return _reviews_student(actor, student)


def _may_request_for_staff(actor: Any, profile: Any) -> bool:
    own = profile.membership_id is not None and profile.membership_id in _mine(actor)
    if own and _holds_anywhere(actor, REQUEST) and _holds_anywhere(actor, STAFF_OWN):
        return True
    return _reviews_staff(actor, profile)


def visible_leave(actor: Any) -> QuerySet[LeaveRequest]:
    """Requests the member made, those of their children or themselves, and those they review."""
    from apps.staff.models import StaffProfile
    from apps.students.models import Student
    from apps.tenancy.models import Campus

    mine = _mine(actor)
    if not mine:
        return LeaveRequest.objects.none()
    grounds = Q(requested_by_id__in=mine)
    grounds |= Q(student__guardian_links__guardian__membership_id__in=mine)
    grounds |= Q(student__membership_id__in=mine) | Q(staff__membership_id__in=mine)
    institutions = set(
        LeaveRequest.objects.values_list("institution_id", flat=True).distinct()
    )  # fmt: skip
    from apps.students.selectors import holds_in_institution

    for inst in institutions:
        if not holds_in_institution(actor, REVIEW, inst):
            continue
        campuses = list(Campus.objects.filter(institution_id=inst).values_list("pk", flat=True))
        if selectors.holds_at(actor, selectors.MANAGE, inst):
            grounds |= Q(institution_id=inst, student__isnull=False)
        else:
            managed = [c for c in campuses if selectors.holds_at(actor, selectors.MANAGE, inst, c)]
            if managed:
                grounds |= Q(
                    institution_id=inst,
                    student__in=Student.objects.filter(
                        enrollments__status="active", enrollments__unit__campus_id__in=managed
                    ),
                )
            units = selectors.advised_units(actor, inst)
            if units:
                grounds |= Q(
                    institution_id=inst,
                    student__in=Student.objects.filter(
                        enrollments__status="active", enrollments__unit_id__in=units
                    ),
                )
        if selectors.holds_at(actor, STAFF_VIEW, inst):
            grounds |= Q(institution_id=inst, staff__isnull=False)
        else:
            seen = [c for c in campuses if selectors.holds_at(actor, STAFF_VIEW, inst, c)]
            if seen:
                grounds |= Q(
                    institution_id=inst,
                    staff__in=StaffProfile.objects.filter(campus_id__in=seen),
                )
    return LeaveRequest.objects.filter(grounds).distinct()


# --------------------------------------------------------------------------- request
def _dates(start: dt.date, end: dt.date, half_day: bool) -> None:
    from apps.attendance.services import today

    if end < start:
        raise ValidationError({"end_date": "The leave ends before it starts."})
    if (end - start).days + 1 > MAX_DAYS:
        raise ValidationError({"end_date": f"At most {MAX_DAYS} days in one request."})
    if start < today() - dt.timedelta(days=MAX_PAST_DAYS):
        raise ValidationError({"start_date": f"At most {MAX_PAST_DAYS} days in the past."})
    if half_day and start != end:
        raise ValidationError({"half_day": "A half day is a single date."})


def _reason(text: Any, limit: int = 500, *, required: bool = True) -> str:
    value = str(text or "").strip()
    if required and not value:
        raise ValidationError({"reason": "Give a reason."})
    if len(value) > limit:
        raise ValidationError({"reason": f"At most {limit} characters."})
    return value


@transaction.atomic
def request_leave(
    *,
    actor: User,
    start_date: dt.date,
    end_date: dt.date,
    reason: str,
    student: Any = None,
    staff: Any = None,
    half_day: bool = False,
    request: HttpRequest | None = None,
) -> LeaveRequest:
    from apps.staff.models import StaffProfile
    from apps.students.models import Student

    if (student is None) == (staff is None):
        raise ValidationError({"person": "Request leave for one student or one staff member."})
    if student is not None:
        kid = Student.objects.select_for_update().filter(pk=getattr(student, "pk", student)).first()
        if kid is None or not _may_request_for_student(actor, kid):
            raise PermissionDenied("You can't request leave for this student.")
        if kid.status != Student.Status.ACTIVE:
            raise ValidationError({"student": "Only active students take leave."})
        who: dict[str, Any] = {"student": kid}
        institution_id = kid.institution_id
    else:
        member = (
            StaffProfile.objects.select_for_update().filter(pk=getattr(staff, "pk", staff)).first()
        )
        if member is None or not _may_request_for_staff(actor, member):
            raise PermissionDenied("You can't request leave for this staff member.")
        who = {"staff": member}
        institution_id = member.institution_id
    _dates(start_date, end_date, half_day)
    text = _reason(reason)
    if LeaveRequest.objects.filter(
        **who, state__in=OPEN, start_date__lte=end_date, end_date__gte=start_date
    ).exists():
        raise ValidationError({"start_date": "Another leave request covers these dates."})
    mine = _mine(actor)
    leave = LeaveRequest.objects.create(
        **who, institution_id=institution_id, start_date=start_date, end_date=end_date,
        half_day=half_day, reason=text, requested_by_id=mine[0] if mine else None,
        created_by=actor.pk,
    )  # fmt: skip
    key = config_for(institution_id).leave_workflow
    if key:
        from apps.customization import workflows

        instance = workflows.start(
            actor=actor, key=key, subject_id=leave.pk,
            context={"subject.kind": "student" if student is not None else "staff",
                     "subject.days": (end_date - start_date).days + 1},
            target=ScopeTarget(require_tenant().id, institution_id),
        )  # fmt: skip
        leave.workflow_instance_id = instance.pk
        leave.save(update_fields=["workflow_instance_id", "updated_at"])
    _audit("attendance.leave.requested", actor, request, leave,
           kind="student" if student is not None else "staff",
           days=(end_date - start_date).days + 1, workflow=bool(key))  # fmt: skip
    return leave


# --------------------------------------------------------------------------- decide, cancel
def _workflow_finished(leave: LeaveRequest) -> bool:
    from apps.customization.models import WorkflowInstance

    if leave.workflow_instance_id is None:
        return True
    return WorkflowInstance.objects.filter(
        pk=leave.workflow_instance_id, finished_at__isnull=False
    ).exists()


def _notify_requester(leave: LeaveRequest) -> None:
    from apps.notifications_core.services import notify

    if leave.requested_by_id is not None:
        notify([leave.requested_by_id], kind="attendance.leave",
               title=f"Leave request {leave.state}", link="/attendance/leave")  # fmt: skip


@transaction.atomic
def decide(
    *,
    actor: User,
    leave: LeaveRequest,
    approve: bool,
    note: str = "",
    request: HttpRequest | None = None,
) -> LeaveRequest:
    row = LeaveRequest.objects.select_for_update().get(pk=leave.pk)
    if not can_review(actor, row):
        raise PermissionDenied("You can't review this leave request.")
    if row.state != LeaveRequest.State.PENDING:
        raise ValidationError({"state": "This request is already decided."})
    if not _workflow_finished(row):
        raise ValidationError({"state": "Finish the approval workflow first."})
    mine = _mine(actor)
    row.state = LeaveRequest.State.APPROVED if approve else LeaveRequest.State.REJECTED
    row.decided_by_id, row.decided_at = (mine[0] if mine else None), timezone.now()
    row.decision_note, row.updated_by = _reason(note, 300, required=False), actor.pk
    row.save(update_fields=["state", "decided_by", "decided_at", "decision_note",
                            "updated_by", "updated_at"])  # fmt: skip
    _audit("attendance.leave.decided", actor, request, row, decision=row.state)
    _notify_requester(row)
    return row


@transaction.atomic
def cancel(*, actor: User, leave: LeaveRequest, request: HttpRequest | None = None) -> LeaveRequest:
    from apps.attendance.services import today

    row = LeaveRequest.objects.select_for_update().get(pk=leave.pk)
    own = row.requested_by_id is not None and row.requested_by_id in _mine(actor)
    if not (own or can_review(actor, row)):
        raise PermissionDenied("You can't cancel this leave request.")
    cancellable = row.state == LeaveRequest.State.PENDING or (
        row.state == LeaveRequest.State.APPROVED and row.start_date > today()
    )
    if not cancellable:
        raise ValidationError({"state": "Only pending or future leave can be cancelled."})
    row.state, row.updated_by = LeaveRequest.State.CANCELLED, actor.pk
    row.save(update_fields=["state", "updated_by", "updated_at"])
    _audit("attendance.leave.cancelled", actor, request, row)
    return row
