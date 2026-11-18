"""Tenant invitations (Phase 3 M4; plan §4.1, §13.2): tokens, authorization, enumeration
safety, acceptance and durable evidence of invalid attempts."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.core.tenancy import tenant_atomic
from apps.core.tokens import hash_token
from apps.rbac import tenant_roles
from apps.rbac.engine import effective_permissions
from apps.rbac.models import RoleAssignment
from apps.rbac.services import GuardRailViolation
from apps.rbac.sources import SELF_SERVICE_CODES as SELF
from apps.tenancy.errors import InvitationEmailMismatch, InvitationInvalid, InvitationRateLimited
from apps.tenancy.models import Invitation, Membership
from apps.tenancy.services import invitations
from tests.helpers import make_user
from tests.isolation.factories import (
    add_member,
    role_codes,
    seed_tenant_roles,
    system_role,
    tenant_events,
)

DURABLE = "audit_durable"
pytestmark = pytest.mark.django_db(databases=["default", DURABLE])


def _invite(org, actor, email, template="teacher", scope="campus", inst=None, campus=None):
    if scope == "campus":
        inst, campus = inst or org.north, campus or org.main
    with tenant_atomic(org.tenant):
        return invitations.create_invitation(
            actor=actor,
            email=email,
            role=tenant_roles.system_role(org.tenant.id, template),
            scope_type=scope,
            institution=inst,
            campus=campus,
        )


def _accept(org, token, user):
    with tenant_atomic(org.tenant):
        return invitations.accept_invitation(token=token, user=user)


def _attempts(org) -> list[str]:
    events = tenant_events(org.tenant, using=DURABLE, action="tenancy.invitation.invalid_attempt")
    return sorted(e.metadata["reason"] for e in events)


def test_invitation_stores_only_the_hash_and_mails_a_tenant_host_link_after_commit(
    org, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        invitation, token = _invite(org, org.owner, "  New.Teacher@Example.com ")
    assert len(callbacks) == 1 and len(mail.outbox) == 1
    assert invitation.email == "new.teacher@example.com"
    assert invitation.token_hash == hash_token(token) and token not in invitation.token_hash
    assert timedelta(days=6, hours=23) < invitation.expires_at - timezone.now() <= timedelta(days=7)
    message = mail.outbox[0]
    assert message.to == ["new.teacher@example.com"]
    assert f"http://acme.tenants.test:8080/en/accept-invitation#token={token}" in message.body
    assert "ACME" in message.subject
    [event] = tenant_events(org.tenant, action="tenancy.invitation.created")
    assert event.metadata == {"role_code": "teacher", "scope_type": "campus"}
    assert token not in str(event.metadata)


def test_a_rolled_back_invitation_sends_nothing(org, django_capture_on_commit_callbacks):
    class AbortError(Exception):
        pass

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        with pytest.raises(AbortError), tenant_atomic(org.tenant):
            invitations.create_invitation(
                actor=org.owner,
                email="x@example.com",
                role=tenant_roles.system_role(org.tenant.id, "teacher"),
                scope_type="tenant",
            )
            raise AbortError
    assert callbacks == [] and mail.outbox == []
    with tenant_atomic(org.tenant):
        assert not Invitation.objects.exists()


def test_inviting_needs_the_permission_in_scope_and_no_escalation(org):
    assert _invite(org, org.head, "a@example.com", "teacher", "institution", org.north)
    # Campus admins and teachers hold no invite permission.
    for actor in (org.campus_admin, org.teacher):
        with pytest.raises(PermissionDenied):
            _invite(org, actor, "b@example.com")
    with pytest.raises(PermissionDenied):  # outside the head's institution
        _invite(org, org.head, "c@example.com", "teacher", "institution", org.south)
    with pytest.raises(PermissionDenied):
        _invite(org, org.head, "c@example.com", "teacher", "tenant")
    with pytest.raises(GuardRailViolation) as exc:  # a role above the inviter
        _invite(org, org.head, "d@example.com", "tenant_owner", "institution", org.north)
    assert exc.value.code == "privilege_escalation"
    for bad in ("", "not-an-email", "x" * 250 + "@example.com"):
        with pytest.raises(ValidationError):
            _invite(org, org.owner, bad)
    with pytest.raises(ValidationError, match="open invitation"):
        _invite(org, org.owner, "A@example.com", "teacher", "institution", org.north)


def test_accepting_creates_the_membership_and_the_offered_assignment(org):
    _, token = _invite(org, org.owner, "new@example.com", "campus_admin")
    person = make_user("new@example.com").user
    membership = _accept(org, token, person)
    assert membership.status == "active" and membership.invited_by == org.owner.pk
    with tenant_atomic(org.tenant):
        assignment = RoleAssignment.objects.get(membership=membership)
        assert (assignment.scope_type, assignment.institution_id, assignment.campus_id) == (
            "campus",
            org.north.pk,
            org.main.pk,
        )
        assert effective_permissions(person, org.t_main, use_cache=True) == (
            role_codes(system_role(org.tenant.id, "campus_admin")) | SELF
        )
        assert Invitation.objects.get(token_hash=hash_token(token)).accepted_at is not None
    # Re-accepting is idempotent for the same person, and "used" for anyone else.
    assert _accept(org, token, person).pk == membership.pk
    other = make_user("other@example.com").user
    with pytest.raises(InvitationInvalid):
        _accept(org, token, other)
    with tenant_atomic(org.tenant):
        assert RoleAssignment.objects.filter(membership=membership).count() == 1
    assert _attempts(org) == ["used"]


def test_every_invalid_token_gets_the_same_answer_and_leaves_evidence(org, tenant_site):
    person = make_user("new@example.com").user
    _, expired = _invite(org, org.owner, "new@example.com", "teacher", "tenant")
    _, revoked = _invite(org, org.owner, "new@example.com", "teacher")
    with tenant_atomic(org.tenant):
        Invitation.objects.filter(token_hash=hash_token(expired)).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        invitations.revoke_invitation(
            actor=org.owner, invitation=Invitation.objects.get(token_hash=hash_token(revoked))
        )
    answers = []
    for token in (expired, revoked, "no-such-token", ""):
        with pytest.raises(InvitationInvalid) as exc:
            _accept(org, token, person)
        answers.append((exc.value.status_code, exc.value.problem_code, str(exc.value.detail)))
    assert len(set(answers)) == 1 and answers[0][:2] == (400, "invitation_invalid")
    assert _attempts(org) == ["expired", "revoked", "unknown", "unknown"]
    with tenant_atomic(org.tenant):
        assert not Membership.objects.filter(user=person).exists()
    # A token of this tenant is unknown in every other tenant.
    other = tenant_site(slug="bravo")
    seed_tenant_roles(other)
    _, good = _invite(org, org.owner, "new@example.com", "teacher", "institution", org.north)
    with pytest.raises(InvitationInvalid), tenant_atomic(other):
        invitations.accept_invitation(token=good, user=person)
    assert _accept(org, good, person).status == "active"


def test_only_the_invited_verified_address_can_accept(org):
    _, token = _invite(org, org.owner, "invited@example.com")
    wrong = make_user("someone-else@example.com").user
    unverified = make_user("invited@example.com", activated=False).user
    for user in (wrong, unverified):
        with pytest.raises(InvitationEmailMismatch) as exc:
            _accept(org, token, user)
        assert (exc.value.status_code, exc.value.problem_code) == (403, "invitation_email_mismatch")
    assert _attempts(org) == ["email_mismatch", "email_mismatch"]
    with tenant_atomic(org.tenant):
        assert Invitation.objects.get(token_hash=hash_token(token)).accepted_at is None


def test_membership_state_at_acceptance(org):
    left = make_user("left@example.com").user
    suspended = make_user("suspended@example.com").user
    add_member(org.tenant, left, status="left")
    add_member(org.tenant, suspended, status="suspended")
    _, t1 = _invite(org, org.owner, "left@example.com")
    _, t2 = _invite(org, org.owner, "suspended@example.com")
    assert _accept(org, t1, left).status == "active"  # a former member can be invited back
    with pytest.raises(InvitationInvalid):  # an old invitation never lifts a suspension
        _accept(org, t2, suspended)
    with tenant_atomic(org.tenant):
        assert Membership.objects.get(user=suspended).status == "suspended"
        assert not RoleAssignment.objects.filter(membership__user=suspended).exists()
    assert _attempts(org) == ["membership_suspended"]


def test_resend_replaces_the_token_and_revoke_closes_the_invitation(
    org, django_capture_on_commit_callbacks
):
    invitation, old = _invite(org, org.owner, "new@example.com")
    person = make_user("new@example.com").user
    with django_capture_on_commit_callbacks(execute=True), tenant_atomic(org.tenant):
        with pytest.raises(PermissionDenied):
            invitations.resend_invitation(actor=org.teacher, invitation=invitation)
        _, new = invitations.resend_invitation(actor=org.owner, invitation=invitation)
    assert new != old and len(mail.outbox) == 1 and new in mail.outbox[0].body
    with pytest.raises(InvitationInvalid):
        _accept(org, old, person)
    with tenant_atomic(org.tenant):
        with pytest.raises(PermissionDenied):
            invitations.revoke_invitation(actor=org.teacher, invitation=invitation)
        assert invitations.revoke_invitation(actor=org.owner, invitation=invitation).revoked_at
        with pytest.raises(InvitationInvalid):
            invitations.resend_invitation(actor=org.owner, invitation=invitation)
    with pytest.raises(InvitationInvalid):
        _accept(org, new, person)
    # After a revoke the same person can be invited again.
    assert _invite(org, org.owner, "new@example.com")


def test_invitations_are_rate_limited_per_address(org, settings):
    limit = settings.SECURITY_THROTTLES["invite_email"][0]
    scopes = [
        ("tenant", None, None),
        ("institution", org.north, None),
        ("campus", org.north, org.main),
        ("campus", org.north, org.annex),
        ("institution", org.south, None),
    ]
    assert len(scopes) == limit
    for scope, inst, campus in scopes:
        _invite(org, org.owner, "busy@example.com", "teacher", scope, inst, campus)
    with pytest.raises(InvitationRateLimited) as exc:
        _invite(org, org.owner, "busy@example.com", "teacher", "campus", org.south, org.south_main)
    assert exc.value.status_code == 429 and exc.value.extra["retry_after"] > 0
    assert _invite(org, org.owner, "calm@example.com")  # another address is unaffected
