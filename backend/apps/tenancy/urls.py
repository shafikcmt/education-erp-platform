"""tenancy routes, mounted under /api/v1/ (Phase 3 M8; plan §12).

Platform-host routes declare their catalogue operation; tenant-host routes are ``TENANT_ONLY``
(the uniform 404 elsewhere). Paths of the two hosts never overlap.
"""

from django.urls import path

from apps.tenancy.api import views_platform as p
from apps.tenancy.api import views_tenant as t

app_name = "tenancy"

urlpatterns = [
    # ---------------------------------------------------------------- platform host
    path("me/memberships/", p.MyMembershipsView.as_view(), name="me-memberships"),
    path("platform/tenants/", p.PlatformTenantsView.as_view(), name="platform-tenants"),
    path(
        "platform/tenants/<str:tenant_id>/",
        p.PlatformTenantDetailView.as_view(),
        name="platform-tenant",
    ),
    path(
        "platform/tenants/<str:tenant_id>/suspend/",
        p.SuspendTenantView.as_view(),
        name="platform-tenant-suspend",
    ),
    path(
        "platform/tenants/<str:tenant_id>/reactivate/",
        p.ReactivateTenantView.as_view(),
        name="platform-tenant-reactivate",
    ),
    path(
        "platform/tenants/<str:tenant_id>/limits/",
        p.TenantLimitsView.as_view(),
        name="platform-tenant-limits",
    ),
    path(
        "platform/tenants/<str:tenant_id>/owner-invitation/",
        p.OwnerInvitationView.as_view(),
        name="platform-tenant-owner-invitation",
    ),
    path(
        "platform/support-sessions/",
        p.OwnSupportSessionsView.as_view(),
        name="platform-support-sessions",
    ),
    path(
        "platform/support-sessions/<str:session_id>/end/",
        p.EndOwnSupportSessionView.as_view(),
        name="platform-support-session-end",
    ),
    # ---------------------------------------------------------------- tenant host
    path("public/tenant/", t.PublicTenantView.as_view(), name="public-tenant"),
    path("me/context/", t.ContextView.as_view(), name="me-context"),
    path("tenant/", t.TenantProfileView.as_view(), name="tenant-profile"),
    path(
        "tenant/support-approval/",
        t.SupportApprovalSettingView.as_view(),
        name="tenant-support-approval",
    ),
    path("institutions/", t.InstitutionsView.as_view(), name="institutions"),
    path(
        "institutions/<str:institution_id>/",
        t.InstitutionDetailView.as_view(),
        name="institution",
    ),
    path(
        "institutions/<str:institution_id>/archive/",
        t.InstitutionArchiveView.as_view(),
        name="institution-archive",
    ),
    path(
        "institutions/<str:institution_id>/campuses/",
        t.CampusesView.as_view(),
        name="institution-campuses",
    ),
    path("campuses/<str:campus_id>/", t.CampusDetailView.as_view(), name="campus"),
    path("campuses/<str:campus_id>/archive/", t.CampusArchiveView.as_view(), name="campus-archive"),
    path("members/", t.MembersView.as_view(), name="members"),
    path("members/<str:member_id>/", t.MemberDetailView.as_view(), name="member"),
    path(
        "members/<str:member_id>/role-assignments/",
        t.MemberAssignmentsView.as_view(),
        name="member-assignments",
    ),
    path(
        "members/<str:member_id>/role-assignments/<str:assignment_id>/",
        t.MemberAssignmentDetailView.as_view(),
        name="member-assignment",
    ),
    path("roles/", t.TenantRolesView.as_view(), name="roles"),
    path("roles/<str:role_id>/", t.TenantRoleDetailView.as_view(), name="role"),
    path("roles/<str:role_id>/clone/", t.TenantRoleCloneView.as_view(), name="role-clone"),
    path("invitations/", t.InvitationsView.as_view(), name="invitations"),
    path(
        "invitations/<str:invitation_id>/",
        t.InvitationDetailView.as_view(),
        name="invitation",
    ),
    path(
        "invitations/<str:invitation_id>/resend/",
        t.InvitationResendView.as_view(),
        name="invitation-resend",
    ),
    path(
        "auth/invitations/accept/",
        t.InvitationAcceptView.as_view(),
        name="invitation-accept",
    ),
    path("support-sessions/", t.SupportSessionsView.as_view(), name="support-sessions"),
    path(
        "support-sessions/<str:session_id>/approve/",
        t.SupportApproveView.as_view(),
        name="support-session-approve",
    ),
    path(
        "support-sessions/<str:session_id>/reject/",
        t.SupportRejectView.as_view(),
        name="support-session-reject",
    ),
    path(
        "support-sessions/<str:session_id>/revoke/",
        t.SupportRevokeView.as_view(),
        name="support-session-revoke",
    ),
    path("audit-events/", t.TenantAuditEventsView.as_view(), name="audit-events"),
    path(
        "audit-events/<str:event_id>/reveal-ip/",
        t.TenantRevealIpView.as_view(),
        name="audit-event-reveal-ip",
    ),
]
