"""Tenant-host tenancy API (Phase 3 M8; plan §12.1).

Every view is tenant-host only (``TENANT_ONLY``): on the platform host it returns the uniform
404. The request already runs in the tenant's transaction (RLS) after the membership gate, so
another tenant's objects are invisible and a foreign id is a plain 404. Permission classes let
a request through when the actor holds the code in some scope of the tenant; lists are
filtered to the scopes the actor covers, and every service checks the exact object scope
again, uncached.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from django.db.models import Q, QuerySet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.audit.api import AuditCursorPagination, AuditEventPageSerializer, AuditEventSerializer
from apps.audit.api import RevealedIpSerializer as RevealedIp
from apps.audit.models import AuditEvent
from apps.audit.services import reveal_ip
from apps.core.hosts import TENANT_ONLY
from apps.core.tenancy import require_tenant
from apps.identity.api.utils import CsrfProtectedView, get_or_404, service_errors
from apps.identity.models import User
from apps.identity.permissions import RequireStepUp
from apps.module_registry.entitlements import summary as entitlement_summary
from apps.module_registry.permissions import ModuleGatedView
from apps.rbac import tenant_roles
from apps.rbac.engine import ScopeTarget, effective_permissions, has_perm
from apps.rbac.models import Role, RoleAssignment
from apps.rbac.permissions import HasPermission
from apps.tenancy.access import membership_status
from apps.tenancy.api import serializers as s
from apps.tenancy.api.permissions import HasTenantPermission, actor_targets
from apps.tenancy.errors import LimitExceededError
from apps.tenancy.limits import LimitExceeded, limits_usage
from apps.tenancy.models import Campus, Institution, Invitation, Membership, SupportSession, Tenant
from apps.tenancy.selectors import support as support_selectors
from apps.tenancy.services import assignments, invitations, memberships, structure
from apps.tenancy.services import support as support_services

TAGS = ["tenant"]


# Tenant-host view: ``module_code`` is checked before the permission (ADR-052). A comment, not
# a docstring: drf-spectacular would publish it as every operation's description.
class TenantView(ModuleGatedView, CsrfProtectedView):
    host_classes = TENANT_ONLY
    module_code = "tenancy"


def _actor(request: Request) -> User:
    assert isinstance(request.user, User)  # noqa: S101 - permission classes guarantee it
    return request.user


def _tenant_id(request: Request) -> Any:
    return require_tenant().id


@contextmanager
def _limit_errors() -> Iterator[None]:
    """``service_errors`` plus the stable ``limit_exceeded`` problem (plan §12.4)."""
    try:
        with service_errors():
            yield
    except LimitExceeded as exc:
        raise LimitExceededError(extra={"kind": exc.kind, "limit": exc.limit}) from exc


def _covered(user: Any, code: str, target: ScopeTarget) -> bool:
    return has_perm(user, code, target=target)


def _sees_institution(user: Any, institution: Institution) -> bool:
    """Visible with ``tenancy.institution.view`` at its scope or at one of its campuses (a
    campus admin sees the institution of their campus, read-only)."""
    code = "tenancy.institution.view"
    if _covered(user, code, structure.institution_target(institution)):
        return True
    return any(
        _covered(user, code, ScopeTarget(institution.tenant_id, institution.pk, campus_id))
        for campus_id in Campus.objects.filter(institution=institution).values_list("pk", flat=True)
    )


# --------------------------------------------------------------------------- public / context
class PublicTenantView(TenantView):
    """Anonymous sign-in page data: name, languages and branding only."""

    permission_classes = [AllowAny]
    tenant_auth_flow = True  # anonymous and not-yet-member callers (sign-in page)

    @extend_schema(
        tags=TAGS,
        summary="Public organisation data for the sign-in page",
        responses=s.PublicTenantSerializer,
    )
    def get(self, request: Request) -> Response:
        tenant = Tenant.objects.get(pk=_tenant_id(request))
        branding = tenant.branding if isinstance(tenant.branding, dict) else {}
        return Response(
            {
                "name": tenant.name,
                "default_locale": tenant.default_locale,
                "locales": tenant.locales or [tenant.default_locale],
                "branding": {k: v for k, v in branding.items() if isinstance(v, str)},
            }
        )


class ContextView(TenantView):
    permission_classes = [HasPermission("identity.account.view_own")]
    suspended_tenant_allowed = True  # owners in restricted mode need their context (D2)

    @extend_schema(
        tags=TAGS,
        summary="My membership, scopes and permissions in this organisation",
        responses=s.ContextSerializer,
    )
    def get(self, request: Request) -> Response:
        user = _actor(request)
        tenant_id = _tenant_id(request)
        session = getattr(request._request, "support_session", None)
        rows = RoleAssignment.objects.filter(
            membership__user_id=user.pk, revoked_at__isnull=True
        ).select_related("role")
        scopes = []
        for target in actor_targets(user, tenant_id):
            scope_type = (
                "campus"
                if target.campus_id
                else "institution"
                if target.institution_id
                else "tenant"
            )
            perms = sorted(effective_permissions(user, target))
            if perms or scope_type == "tenant":
                scopes.append(
                    {
                        "scope_type": scope_type,
                        "institution": target.institution_id,
                        "campus": target.campus_id,
                        "permissions": perms,
                    }
                )
        tenant = Tenant.objects.get(pk=tenant_id)
        data = {
            "tenant": tenant,
            "membership_status": membership_status(user.pk),
            "is_support_session": session is not None,
            "support_session_ends_at": getattr(session, "ends_at", None),
            "assignments": list(rows),
            "scopes": scopes,
            "support_banner": support_selectors.banner(),
            "entitlements": {
                **entitlement_summary(tenant_id),
                "limits": limits_usage(tenant),
            },
        }
        return Response(s.ContextSerializer(data).data)


# --------------------------------------------------------------------------- profile
class TenantProfileView(TenantView):
    # Every member template holds ``tenancy.tenant.view`` in its own scope; changing the
    # profile needs ``tenancy.tenant.update`` at tenant scope (checked by the service).
    permission_classes = [
        HasTenantPermission({"GET": "tenancy.tenant.view", "PATCH": "tenancy.tenant.update"})
    ]

    @extend_schema(tags=TAGS, summary="Organisation profile", responses=s.TenantProfileSerializer)
    def get(self, request: Request) -> Response:
        return Response(s.TenantProfileSerializer(Tenant.objects.get(pk=_tenant_id(request))).data)

    @extend_schema(
        tags=TAGS,
        summary="Update the organisation profile",
        request=s.TenantProfileUpdateSerializer,
        responses=s.TenantProfileSerializer,
    )
    def patch(self, request: Request) -> Response:
        data = s.TenantProfileUpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        with service_errors():
            tenant = structure.update_profile(
                actor=_actor(request), changes=dict(data.validated_data), request=request._request
            )
        return Response(s.TenantProfileSerializer(tenant).data)


class SupportApprovalSettingView(TenantView):
    """D5: owners only, with a reason and a fresh step-up."""

    permission_classes = [HasPermission({"POST": "tenancy.tenant.update"}), RequireStepUp]

    @extend_schema(
        tags=TAGS,
        summary="Require (or stop requiring) approval of support access",
        request=s.SupportApprovalSerializer,
        responses=s.TenantProfileSerializer,
    )
    def post(self, request: Request) -> Response:
        data = s.SupportApprovalSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with service_errors():
            support_services.set_approval_required(
                actor=_actor(request),
                required=data.validated_data["requires_approval"],
                reason=data.validated_data["reason"],
                request=request._request,
            )
        return Response(s.TenantProfileSerializer(Tenant.objects.get(pk=_tenant_id(request))).data)


# --------------------------------------------------------------------------- institutions
def _institution(request: Request, institution_id: str) -> Institution:
    institution = get_or_404(Institution.objects.all(), institution_id)
    if not _sees_institution(request.user, institution):
        raise NotFound()  # outside the actor's scopes: as if it did not exist
    return institution


class InstitutionsView(TenantView):
    permission_classes = [
        HasTenantPermission(
            {"GET": "tenancy.institution.view", "POST": "tenancy.institution.create"}
        )
    ]

    @extend_schema(
        tags=TAGS, summary="Institutions I can see", responses=s.InstitutionSerializer(many=True)
    )
    def get(self, request: Request) -> Response:
        rows = [
            i for i in Institution.objects.order_by("code") if _sees_institution(request.user, i)
        ]
        return Response(s.InstitutionSerializer(rows, many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Create an institution (limit applies)",
        request=s.InstitutionCreateSerializer,
        responses={201: s.InstitutionSerializer},
    )
    def post(self, request: Request) -> Response:
        data = s.InstitutionCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with _limit_errors():
            institution = structure.create_institution(
                actor=_actor(request), request=request._request, **data.validated_data
            )
        return Response(s.InstitutionSerializer(institution).data, status=status.HTTP_201_CREATED)


class InstitutionDetailView(TenantView):
    permission_classes = [
        HasTenantPermission(
            {"GET": "tenancy.institution.view", "PATCH": "tenancy.institution.update"}
        )
    ]

    @extend_schema(tags=TAGS, summary="Institution", responses=s.InstitutionSerializer)
    def get(self, request: Request, institution_id: str) -> Response:
        institution = _institution(request, institution_id)
        return Response(s.InstitutionSerializer(institution).data)

    @extend_schema(
        tags=TAGS,
        summary="Update an institution",
        request=s.InstitutionUpdateSerializer,
        responses=s.InstitutionSerializer,
    )
    def patch(self, request: Request, institution_id: str) -> Response:
        institution = _institution(request, institution_id)
        data = s.InstitutionUpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        with service_errors():
            institution = structure.update_institution(
                actor=_actor(request),
                institution=institution,
                changes=dict(data.validated_data),
                request=request._request,
            )
        return Response(s.InstitutionSerializer(institution).data)


class InstitutionArchiveView(TenantView):
    permission_classes = [HasTenantPermission({"POST": "tenancy.institution.archive"})]

    @extend_schema(
        tags=TAGS,
        summary="Archive an institution and its campuses (step-up)",
        request=None,
        responses=s.InstitutionSerializer,
    )
    def post(self, request: Request, institution_id: str) -> Response:
        institution = _institution(request, institution_id)
        with service_errors():
            institution = structure.archive_institution(
                actor=_actor(request), institution=institution, request=request._request
            )
        return Response(s.InstitutionSerializer(institution).data)


# --------------------------------------------------------------------------- campuses
def _campus(request: Request, campus_id: str) -> Campus:
    campus = get_or_404(Campus.objects.all(), campus_id)
    if not _covered(request.user, "tenancy.campus.view", structure.campus_target(campus)):
        raise NotFound()
    return campus


class CampusesView(TenantView):
    permission_classes = [
        HasTenantPermission({"GET": "tenancy.campus.view", "POST": "tenancy.campus.create"})
    ]

    @extend_schema(
        tags=TAGS, summary="Campuses of an institution", responses=s.CampusSerializer(many=True)
    )
    def get(self, request: Request, institution_id: str) -> Response:
        institution = _institution(request, institution_id)
        rows = [
            c
            for c in Campus.objects.filter(institution=institution).order_by("code")
            if _covered(request.user, "tenancy.campus.view", structure.campus_target(c))
        ]
        return Response(s.CampusSerializer(rows, many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Create a campus (limit applies)",
        request=s.CampusCreateSerializer,
        responses={201: s.CampusSerializer},
    )
    def post(self, request: Request, institution_id: str) -> Response:
        institution = _institution(request, institution_id)
        data = s.CampusCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        with _limit_errors():
            campus = structure.create_campus(
                actor=_actor(request),
                institution=institution,
                code=values["code"],
                name=values["name"],
                name_i18n=values.get("name_i18n"),
                address=values.get("address"),
                timezone_name=values.get("timezone", ""),
                request=request._request,
            )
        return Response(s.CampusSerializer(campus).data, status=status.HTTP_201_CREATED)


class CampusDetailView(TenantView):
    permission_classes = [
        HasTenantPermission({"GET": "tenancy.campus.view", "PATCH": "tenancy.campus.update"})
    ]

    @extend_schema(tags=TAGS, summary="Campus", responses=s.CampusSerializer)
    def get(self, request: Request, campus_id: str) -> Response:
        return Response(s.CampusSerializer(_campus(request, campus_id)).data)

    @extend_schema(
        tags=TAGS,
        summary="Update a campus or make it the main campus",
        request=s.CampusUpdateSerializer,
        responses=s.CampusSerializer,
    )
    def patch(self, request: Request, campus_id: str) -> Response:
        campus = _campus(request, campus_id)
        data = s.CampusUpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        changes = dict(data.validated_data)
        make_main = bool(changes.pop("make_main", False))
        with service_errors():
            campus = structure.update_campus(
                actor=_actor(request),
                campus=campus,
                changes=changes,
                make_main=make_main,
                request=request._request,
            )
        return Response(s.CampusSerializer(campus).data)


class CampusArchiveView(TenantView):
    permission_classes = [HasTenantPermission({"POST": "tenancy.campus.archive"})]

    @extend_schema(
        tags=TAGS, summary="Archive a campus (step-up)", request=None, responses=s.CampusSerializer
    )
    def post(self, request: Request, campus_id: str) -> Response:
        campus = _campus(request, campus_id)
        with service_errors():
            campus = structure.archive_campus(
                actor=_actor(request), campus=campus, request=request._request
            )
        return Response(s.CampusSerializer(campus).data)


# --------------------------------------------------------------------------- members
def _member_filter(user: Any, code: str, tenant_id: Any) -> Q | None:
    """``None``: the actor sees every member; else members with an assignment in a scope the
    actor covers with ``code``."""
    if has_perm(user, code, target=ScopeTarget(tenant_id)):
        return None
    q = Q(pk__in=[])
    for target in actor_targets(user, tenant_id)[1:]:
        if not has_perm(user, code, target=target):
            continue
        scoped = Q(role_assignments__institution_id=target.institution_id)
        if target.campus_id is not None:
            scoped &= Q(role_assignments__campus_id=target.campus_id)
        q |= scoped & Q(role_assignments__revoked_at__isnull=True)
    return q


def _members(request: Request, code: str = "tenancy.member.view") -> QuerySet[Membership]:
    rows = Membership.objects.select_related("user")
    q = _member_filter(request.user, code, _tenant_id(request))
    return rows if q is None else rows.filter(q).distinct()


class MembersView(TenantView):
    permission_classes = [HasTenantPermission({"GET": "tenancy.member.view"})]

    @extend_schema(tags=TAGS, summary="Members I can see", responses=s.MemberSerializer(many=True))
    def get(self, request: Request) -> Response:
        rows = _members(request).order_by("user__email")
        if value := request.query_params.get("status"):
            rows = rows.filter(status=value[:16])
        return Response(s.MemberSerializer(rows, many=True).data)


class MemberDetailView(TenantView):
    permission_classes = [
        HasTenantPermission(
            {
                "GET": "tenancy.member.view",
                "PATCH": "tenancy.member.update",
                "DELETE": "tenancy.member.remove",
            }
        )
    ]

    @extend_schema(tags=TAGS, summary="Member", responses=s.MemberSerializer)
    def get(self, request: Request, member_id: str) -> Response:
        return Response(s.MemberSerializer(get_or_404(_members(request), member_id)).data)

    @extend_schema(
        tags=TAGS,
        summary="Suspend or reactivate a member",
        request=s.MemberUpdateSerializer,
        responses=s.MemberSerializer,
    )
    def patch(self, request: Request, member_id: str) -> Response:
        membership = get_or_404(_members(request), member_id)
        data = s.MemberUpdateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        service = (
            memberships.suspend_member
            if data.validated_data["status"] == "suspended"
            else memberships.reactivate_member
        )
        with service_errors():
            membership = service(
                actor=_actor(request), membership=membership, request=request._request
            )
        return Response(s.MemberSerializer(membership).data)

    @extend_schema(tags=TAGS, summary="Remove a member (step-up)", responses={204: None})
    def delete(self, request: Request, member_id: str) -> Response:
        membership = get_or_404(_members(request), member_id)
        with service_errors():
            memberships.remove_member(
                actor=_actor(request), membership=membership, request=request._request
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MemberAssignmentsView(TenantView):
    module_code = "rbac"
    permission_classes = [
        HasTenantPermission({"GET": "rbac.assignment.view", "POST": "rbac.assignment.manage"})
    ]

    @extend_schema(
        tags=TAGS,
        summary="A member's role assignments",
        responses=s.TenantAssignmentSerializer(many=True),
    )
    def get(self, request: Request, member_id: str) -> Response:
        membership = get_or_404(_members(request, "rbac.assignment.view"), member_id)
        rows = [
            a
            for a in RoleAssignment.objects.filter(membership=membership)
            .select_related("role")
            .order_by("-valid_from")
            if _covered(
                request.user,
                "rbac.assignment.view",
                ScopeTarget(a.tenant_id, a.institution_id, a.campus_id),
            )
        ]
        return Response(s.TenantAssignmentSerializer(rows, many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Grant a role in a scope (step-up)",
        request=s.TenantAssignmentCreateSerializer,
        responses={201: s.TenantAssignmentSerializer},
    )
    def post(self, request: Request, member_id: str) -> Response:
        membership = get_or_404(_members(request, "rbac.assignment.view"), member_id)
        data = s.TenantAssignmentCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        with service_errors():
            assignment = assignments.grant_assignment(
                actor=_actor(request),
                membership=membership,
                role=values["role"],
                scope_type=values["scope_type"],
                institution=values["institution"],
                campus=values["campus"],
                valid_until=values["valid_until"],
                reason=values["reason"],
                request=request._request,
            )
        assignment = RoleAssignment.objects.select_related("role").get(pk=assignment.pk)
        return Response(
            s.TenantAssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED
        )


class MemberAssignmentDetailView(TenantView):
    module_code = "rbac"
    permission_classes = [HasTenantPermission({"DELETE": "rbac.assignment.manage"})]

    @extend_schema(tags=TAGS, summary="Revoke a role assignment (step-up)", responses={204: None})
    def delete(self, request: Request, member_id: str, assignment_id: str) -> Response:
        membership = get_or_404(_members(request, "rbac.assignment.view"), member_id)
        assignment = get_or_404(RoleAssignment.objects.filter(membership=membership), assignment_id)
        with service_errors():
            assignments.revoke_assignment(
                actor=_actor(request), assignment=assignment, request=request._request
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- roles
def _roles(request: Request) -> QuerySet[Role]:
    return tenant_roles.tenant_roles(_tenant_id(request)).select_related("template")


class TenantRolesView(TenantView):
    module_code = "rbac"
    permission_classes = [HasTenantPermission({"GET": "rbac.role.view"})]

    @extend_schema(
        tags=TAGS, summary="Roles of this organisation", responses=s.TenantRoleSerializer(many=True)
    )
    def get(self, request: Request) -> Response:
        return Response(s.TenantRoleSerializer(_roles(request).order_by("code"), many=True).data)


class TenantRoleDetailView(TenantView):
    module_code = "rbac"
    permission_classes = [
        HasPermission(
            {"GET": "rbac.role.view", "PATCH": "rbac.role.update", "DELETE": "rbac.role.delete"}
        )
    ]

    @extend_schema(tags=TAGS, summary="Role", responses=s.TenantRoleSerializer)
    def get(self, request: Request, role_id: str) -> Response:
        return Response(s.TenantRoleSerializer(get_or_404(_roles(request), role_id)).data)

    @extend_schema(
        tags=TAGS,
        summary="Update a custom role (step-up)",
        request=s.TenantRoleUpdateSerializer,
        responses=s.TenantRoleSerializer,
    )
    def patch(self, request: Request, role_id: str) -> Response:
        role = get_or_404(_roles(request), role_id)
        data = s.TenantRoleUpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        with service_errors():
            tenant_roles.update_tenant_role(
                actor=_actor(request),
                tenant_id=_tenant_id(request),
                role=role,
                changes=dict(data.validated_data),
                request=request._request,
            )
        return Response(s.TenantRoleSerializer(get_or_404(_roles(request), role_id)).data)

    @extend_schema(
        tags=TAGS, summary="Delete an unused custom role (step-up)", responses={204: None}
    )
    def delete(self, request: Request, role_id: str) -> Response:
        role = get_or_404(_roles(request), role_id)
        with service_errors():
            tenant_roles.delete_tenant_role(
                actor=_actor(request),
                tenant_id=_tenant_id(request),
                role=role,
                request=request._request,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class TenantRoleCloneView(TenantView):
    module_code = "rbac"
    permission_classes = [HasPermission({"POST": "rbac.role.clone"})]

    @extend_schema(
        tags=TAGS,
        summary="Clone a role into an editable role (step-up)",
        request=s.TenantRoleCloneSerializer,
        responses={201: s.TenantRoleSerializer},
    )
    def post(self, request: Request, role_id: str) -> Response:
        source = get_or_404(_roles(request), role_id)
        data = s.TenantRoleCloneSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with service_errors():
            clone = tenant_roles.clone_role(
                actor=_actor(request),
                tenant_id=_tenant_id(request),
                source=source,
                request=request._request,
                **data.validated_data,
            )
        return Response(
            s.TenantRoleSerializer(get_or_404(_roles(request), clone.pk)).data,
            status=status.HTTP_201_CREATED,
        )


# --------------------------------------------------------------------------- invitations
def _invitation_target(invitation: Invitation) -> ScopeTarget:
    return ScopeTarget(invitation.tenant_id, invitation.institution_id, invitation.campus_id)


def _invitation(request: Request, invitation_id: str) -> Invitation:
    invitation = get_or_404(Invitation.objects.select_related("role"), invitation_id)
    if not _covered(request.user, "tenancy.member.invite", _invitation_target(invitation)):
        raise NotFound()
    return invitation


class InvitationsView(TenantView):
    permission_classes = [HasTenantPermission("tenancy.member.invite")]

    @extend_schema(
        tags=TAGS, summary="Open invitations I manage", responses=s.InvitationSerializer(many=True)
    )
    def get(self, request: Request) -> Response:
        rows = [
            i
            for i in Invitation.objects.filter(accepted_at__isnull=True, revoked_at__isnull=True)
            .select_related("role")
            .order_by("-created_at")
            if _covered(request.user, "tenancy.member.invite", _invitation_target(i))
        ]
        return Response(s.InvitationSerializer(rows, many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Invite someone with a role in a scope",
        request=s.InvitationCreateSerializer,
        responses={201: s.InvitationSerializer},
    )
    def post(self, request: Request) -> Response:
        data = s.InvitationCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with service_errors():
            invitation, _ = invitations.create_invitation(
                actor=_actor(request), request=request._request, **data.validated_data
            )
        return Response(s.InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)


class InvitationDetailView(TenantView):
    permission_classes = [HasTenantPermission({"DELETE": "tenancy.member.invite"})]

    @extend_schema(tags=TAGS, summary="Revoke an invitation", responses={204: None})
    def delete(self, request: Request, invitation_id: str) -> Response:
        invitation = _invitation(request, invitation_id)
        with service_errors():
            invitations.revoke_invitation(
                actor=_actor(request), invitation=invitation, request=request._request
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvitationResendView(TenantView):
    permission_classes = [HasTenantPermission({"POST": "tenancy.member.invite"})]

    @extend_schema(
        tags=TAGS,
        summary="Send an invitation again with a new link",
        request=None,
        responses=s.InvitationSerializer,
    )
    def post(self, request: Request, invitation_id: str) -> Response:
        invitation = _invitation(request, invitation_id)
        with service_errors():
            invitation, _ = invitations.resend_invitation(
                actor=_actor(request), invitation=invitation, request=request._request
            )
        return Response(s.InvitationSerializer(invitation).data)


class InvitationAcceptView(TenantView):
    """Redeem an invitation: as the signed-in account, or with a password (creating the account
    or proving the existing one; a non-member can't sign in here, D7). Unknown, expired, used
    and revoked tokens get one answer (``invitation_invalid``); every failure leaves durable
    evidence."""

    permission_classes = [AllowAny]
    tenant_auth_flow = True  # the caller is not a member yet

    @extend_schema(
        tags=TAGS,
        summary="Accept an invitation",
        request=s.InvitationAcceptSerializer,
        responses=s.InvitationAcceptedSerializer,
    )
    def post(self, request: Request) -> Response:
        data = s.InvitationAcceptSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        user = request.user
        with service_errors():
            if isinstance(user, User) and user.is_authenticated:
                membership = invitations.accept_invitation(
                    token=values["token"], user=user, request=request._request
                )
                created = False
            else:
                if not values.get("password"):
                    raise ValidationError({"password": "Enter your password, or choose one."})
                membership, _, created = invitations.accept_without_session(
                    token=values["token"],
                    password=values["password"],
                    display_name=values.get("display_name", ""),
                    locale=values["locale"],
                    request=request._request,
                )
        return Response(
            {"membership": membership.pk, "status": membership.status, "account_created": created}
        )


# --------------------------------------------------------------------------- support sessions
class SupportSessionsView(TenantView):
    permission_classes = [HasPermission({"GET": "tenancy.support_session.view"})]
    suspended_tenant_allowed = True

    @extend_schema(
        tags=TAGS, summary="Support access history", responses=s.SupportSessionSerializer(many=True)
    )
    def get(self, request: Request) -> Response:
        rows = SupportSession.objects.order_by("-requested_at")
        return Response(s.SupportSessionSerializer(rows, many=True).data)


class _SupportDecisionView(TenantView):
    suspended_tenant_allowed = True
    service: Any = None

    def post(self, request: Request, session_id: str) -> Response:
        session = get_or_404(SupportSession.objects.all(), session_id)
        with service_errors():
            session = type(self).service(
                actor=_actor(request), session=session, request=request._request
            )
        return Response(s.SupportSessionSerializer(session).data)


class SupportApproveView(_SupportDecisionView):
    permission_classes = [HasPermission({"POST": "tenancy.support_session.approve"})]
    service = staticmethod(support_services.approve_session)

    @extend_schema(
        tags=TAGS,
        summary="Approve support access (step-up)",
        request=None,
        responses=s.SupportSessionSerializer,
    )
    def post(self, request: Request, session_id: str) -> Response:
        return super().post(request, session_id)


class SupportRejectView(_SupportDecisionView):
    permission_classes = [HasPermission({"POST": "tenancy.support_session.approve"})]
    service = staticmethod(support_services.reject_session)

    @extend_schema(
        tags=TAGS,
        summary="Reject a support request (step-up)",
        request=None,
        responses=s.SupportSessionSerializer,
    )
    def post(self, request: Request, session_id: str) -> Response:
        return super().post(request, session_id)


class SupportRevokeView(_SupportDecisionView):
    permission_classes = [HasPermission({"POST": "tenancy.support_session.revoke"})]
    service = staticmethod(support_services.revoke_session)

    @extend_schema(
        tags=TAGS,
        summary="Revoke support access",
        request=None,
        responses=s.SupportSessionSerializer,
    )
    def post(self, request: Request, session_id: str) -> Response:
        return super().post(request, session_id)


# --------------------------------------------------------------------------- audit log
class TenantAuditEventsView(TenantView):
    module_code = "audit"
    permission_classes = [HasPermission("audit.event.view")]

    @extend_schema(
        tags=TAGS,
        operation_id="tenant_audit_events_list",
        parameters=[
            OpenApiParameter("action", OpenApiTypes.STR),
            OpenApiParameter("outcome", OpenApiTypes.STR),
            OpenApiParameter("target_type", OpenApiTypes.STR),
            OpenApiParameter("cursor", OpenApiTypes.STR),
            OpenApiParameter("page_size", OpenApiTypes.INT),
        ],
        summary="This organisation's audit log (cursor pagination)",
        responses=AuditEventPageSerializer,
    )
    def get(self, request: Request) -> Response:
        events = AuditEvent.objects.filter(tenant_id=_tenant_id(request)).select_related("ip")
        params = request.query_params
        for name in ("action", "outcome", "target_type"):
            if value := params.get(name):
                events = events.filter(**{name: value[:120]})
        paginator = AuditCursorPagination()
        page = paginator.paginate_queryset(events, request, view=self)
        return paginator.get_paginated_response(AuditEventSerializer(page, many=True).data)


class TenantRevealIpView(TenantView):
    module_code = "audit"
    permission_classes = [HasPermission("audit.event.view_ip")]

    @extend_schema(
        tags=TAGS,
        summary="Reveal an event's IP (step-up; audited)",
        request=None,
        responses=RevealedIp,
    )
    def post(self, request: Request, event_id: str) -> Response:
        event = get_or_404(AuditEvent.objects.filter(tenant_id=_tenant_id(request)), event_id)
        return Response({"ip": reveal_ip(event, actor=_actor(request), request=request._request)})
