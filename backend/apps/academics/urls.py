"""Academics routes (Phase 6 M2). Tenant host only."""

from django.urls import path

from apps.academics.api import views as v

app_name = "academics"

urlpatterns = [
    path("academics/setup/", v.SetupView.as_view(), name="setup"),
    path("academics/years/", v.YearsView.as_view(), name="years"),
    path("academics/years/<str:year_id>/status/", v.YearStatusView.as_view(), name="year-status"),
    path("academics/years/<str:year_id>/terms/", v.TermsView.as_view(), name="terms"),
    path("academics/units/", v.UnitsView.as_view(), name="units"),
    path("academics/units/<str:unit_id>/", v.UnitDetailView.as_view(), name="unit"),
    path(
        "academics/units/<str:unit_id>/archive/", v.UnitArchiveView.as_view(), name="unit-archive"
    ),
    path("academics/subjects/", v.SubjectsView.as_view(), name="subjects"),
    path(
        "academics/subjects/<str:subject_id>/archive/",
        v.SubjectArchiveView.as_view(),
        name="subject-archive",
    ),
    path("academics/offerings/", v.OfferingsView.as_view(), name="offerings"),
    path(
        "academics/offerings/<str:offering_id>/teachers/",
        v.OfferingTeachersView.as_view(),
        name="offering-teachers",
    ),
    path(
        "academics/offerings/<str:offering_id>/teachers/<str:teacher_id>/",
        v.OfferingTeacherDetailView.as_view(),
        name="offering-teacher",
    ),
]
