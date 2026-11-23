"""Admissions routes (Phase 6 M4). Tenant host only."""

from django.urls import path

from apps.admissions.api import public as p
from apps.admissions.api import views as v

app_name = "admissions"

urlpatterns = [
    path("admissions/inquiries/", v.InquiriesView.as_view(), name="inquiries"),
    path("admissions/inquiries/<str:inquiry_id>/", v.InquiryDetailView.as_view(), name="inquiry"),
    path("admissions/cycles/", v.CyclesView.as_view(), name="cycles"),
    path(
        "admissions/cycles/<str:cycle_id>/targets/",
        v.CycleTargetsView.as_view(),
        name="cycle-targets",
    ),
    path(
        "admissions/cycles/<str:cycle_id>/status/", v.CycleStatusView.as_view(), name="cycle-status"
    ),
    path("admissions/applications/", v.ApplicationsView.as_view(), name="applications"),
    path(
        "admissions/applications/<str:application_id>/",
        v.ApplicationDetailView.as_view(),
        name="application",
    ),
    path(
        "admissions/applications/<str:application_id>/review/",
        v.ApplicationReviewView.as_view(),
        name="application-review",
    ),
    path(
        "admissions/applications/<str:application_id>/decision/",
        v.ApplicationDecisionView.as_view(),
        name="application-decision",
    ),
    path(
        "admissions/applications/<str:application_id>/offer-response/",
        v.OfferResponseView.as_view(),
        name="application-offer-response",
    ),
    path(
        "admissions/applications/<str:application_id>/documents/",
        v.ApplicationDocumentsView.as_view(),
        name="application-documents",
    ),
    path(
        "admissions/applications/<str:application_id>/documents/<str:file_id>/download/",
        v.ApplicationDocumentDownloadView.as_view(),
        name="application-document-download",
    ),
    # ------------------------------------------------------------- tests and merit (M6)
    path("admissions/cycles/<str:cycle_id>/tests/", v.CycleTestsView.as_view(), name="cycle-tests"),
    path(
        "admissions/tests/<str:test_id>/assignments/",
        v.TestAssignmentsView.as_view(),
        name="test-assignments",
    ),
    path(
        "admissions/assignments/<str:assignment_id>/",
        v.AssignmentScoreView.as_view(),
        name="assignment-score",
    ),
    path(
        "admissions/applications/<str:application_id>/evaluate/",
        v.ApplicationEvaluateView.as_view(),
        name="application-evaluate",
    ),
    path("admissions/targets/<str:target_id>/merit/", v.TargetMeritView.as_view(), name="merit"),
    path(
        "admissions/targets/<str:target_id>/merit/publish/",
        v.TargetMeritPublishView.as_view(),
        name="merit-publish",
    ),
    path(
        "admissions/targets/<str:target_id>/merit/offers/",
        v.TargetMeritOffersView.as_view(),
        name="merit-offers",
    ),
    # ------------------------------------------------------------- public (anonymous, M5)
    path("public/admissions/cycles/", p.OpenCyclesView.as_view(), name="public-cycles"),
    path(
        "public/admissions/cycles/<str:cycle_id>/form/",
        p.CycleFormView.as_view(),
        name="public-cycle-form",
    ),
    path(
        "public/admissions/cycles/<str:cycle_id>/visibility/",
        p.CycleVisibilityView.as_view(),
        name="public-cycle-visibility",
    ),
    path(
        "public/admissions/cycles/<str:cycle_id>/apply/",
        p.SubmitView.as_view(),
        name="public-apply",
    ),
    path("public/admissions/verify/", p.VerifyView.as_view(), name="public-verify"),
    path("public/admissions/status/", p.StatusView.as_view(), name="public-status"),
    path("public/admissions/status/respond/", p.RespondView.as_view(), name="public-respond"),
    path(
        "public/admissions/status/documents/",
        p.DocumentSlotView.as_view(),
        name="public-document-slot",
    ),
    path(
        "public/admissions/status/documents/confirm/",
        p.DocumentConfirmView.as_view(),
        name="public-document-confirm",
    ),
]
