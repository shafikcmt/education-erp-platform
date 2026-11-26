"""Students routes (Phase 7 M2). Tenant host only."""

from django.urls import path

from apps.students.api import views as v

app_name = "students"

urlpatterns = [
    path("students/", v.StudentsView.as_view(), name="students"),
    path("students/<str:student_id>/", v.StudentDetailView.as_view(), name="student"),
    path(
        "students/<str:student_id>/guardians/",
        v.StudentGuardiansView.as_view(),
        name="student-guardians",
    ),
    path(
        "students/<str:student_id>/guardians/<str:link_id>/",
        v.StudentGuardianLinkView.as_view(),
        name="student-guardian",
    ),
    path(
        "students/<str:student_id>/enrollments/",
        v.StudentEnrollmentsView.as_view(),
        name="student-enrollments",
    ),
    path("guardians/", v.GuardiansView.as_view(), name="guardians"),
    path("guardians/merge/", v.GuardianMergeView.as_view(), name="guardian-merge"),
]
