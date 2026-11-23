"""Admissions routes (Phase 6 M4). Tenant host only."""

from django.urls import path

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
]
