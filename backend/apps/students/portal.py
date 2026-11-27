"""Portal invitations for guardians and students (Phase 7 M8; ADR-069; plan §3).

A guardian or a student with an email address is invited to the organisation through the
Phase 3 invitation flow (the email, the single-use token, acceptance with or without an existing
account). The role is the tenant's system copy of ``guardian`` or ``student``, granted in the
student's institution; :func:`tenancy.services.invitations.create_invitation` checks the
inviter's ``tenancy.member.invite`` and that they hold every code of that role (no escalation).

On acceptance, :func:`on_invitation_accepted` (``TENANCY_INVITATION_ACCEPTED_HANDLERS``) links
the new login to the record, in the acceptance transaction. One account serves several children,
and a guardian who is also staff keeps one account. Phone-only guardians stay without a login
until phone sign-in exists (ADR-074 Q2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.students import services
from apps.students.models import Guardian, PortalInvite, Student, StudentGuardian

if TYPE_CHECKING:
    from apps.identity.models import User
    from apps.tenancy.models import Invitation, Membership


def _role(code: str) -> Any:
    from apps.core.tenancy import require_tenant
    from apps.rbac.tenant_roles import system_role

    return system_role(require_tenant().id, code)


def _invite(
    actor: User, *, kind: str, record: Any, email: str, institution_id: Any,
    request: HttpRequest | None,
) -> PortalInvite:  # fmt: skip
    from apps.rbac.models import AssignmentScope
    from apps.tenancy.services.invitations import create_invitation

    if not email:
        raise ValidationError({"email": "Add an email address first (phone sign-in comes later)."})
    if record.membership_id is not None:
        raise ValidationError({"membership": "This person already has a login."})
    invitation, _ = create_invitation(
        actor=actor, email=email, role=_role(kind).pk, scope_type=AssignmentScope.INSTITUTION,
        institution=institution_id, request=request,
    )  # fmt: skip
    row = PortalInvite.objects.create(
        invitation_id=invitation.pk, kind=kind, record_id=record.pk, created_by=actor.pk
    )
    services._audit("students.portal.invited", actor, request, record, kind=kind)
    return row


@transaction.atomic
def invite_guardian(
    *, actor: User, guardian: Guardian, request: HttpRequest | None = None
) -> PortalInvite:
    """Invite a guardian (``students.guardian.manage`` in every institution where they have a
    child, like a merge)."""
    guardian = Guardian.objects.select_for_update().get(pk=guardian.pk)
    institutions = sorted(
        set(
            Student.objects.filter(
                pk__in=StudentGuardian.objects.filter(guardian=guardian).values("student_id")
            ).values_list("institution_id", flat=True)
        ),
        key=str,
    )
    if not institutions:
        raise ValidationError({"guardian": "Link the guardian to a student first."})
    for institution_id in institutions:
        services._authorise(actor, services.GUARDIANS, institution_id)
    return _invite(actor, kind=PortalInvite.Kind.GUARDIAN, record=guardian, email=guardian.email,
                   institution_id=institutions[0], request=request)  # fmt: skip


@transaction.atomic
def invite_student(
    *, actor: User, student: Student, request: HttpRequest | None = None
) -> PortalInvite:
    student = Student.objects.select_for_update().get(pk=student.pk)
    services._authorise(actor, services.MANAGE, student.institution_id)
    if student.status != Student.Status.ACTIVE:
        raise ValidationError({"student": "Only active students are invited."})
    return _invite(actor, kind=PortalInvite.Kind.STUDENT, record=student, email=student.email,
                   institution_id=student.institution_id, request=request)  # fmt: skip


def on_invitation_accepted(*, invitation: Invitation, membership: Membership) -> None:
    """``TENANCY_INVITATION_ACCEPTED_HANDLERS``: link the login to the invited record (once; a
    record that got another login meanwhile, or a login already linked to another record of
    the same kind, is left alone)."""
    invite = (
        PortalInvite.objects.select_for_update()
        .filter(invitation_id=invitation.pk, linked_at__isnull=True)
        .first()
    )
    if invite is None:
        return
    model: Any = Guardian if invite.kind == PortalInvite.Kind.GUARDIAN else Student
    if model.objects.filter(membership=membership).exists():
        return
    linked = model.objects.filter(pk=invite.record_id, membership__isnull=True).update(
        membership=membership, updated_at=timezone.now()
    )
    if linked:
        invite.linked_at = timezone.now()
        invite.save(update_fields=["linked_at", "updated_at"])
