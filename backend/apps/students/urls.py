"""Students routes (Phase 7 M2). Tenant host only."""

from django.urls import path

from apps.students.api import views as v

app_name = "students"

urlpatterns = [
    path("students/", v.StudentsView.as_view(), name="students"),
    path("students/promotion/preview/", v.PromotionPreviewView.as_view(), name="promotion-preview"),
    path("students/promotion/apply/", v.PromotionApplyView.as_view(), name="promotion-apply"),
    path(
        "students/from-application/",
        v.StudentFromApplicationView.as_view(),
        name="student-from-application",
    ),
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
    path("students/<str:student_id>/move/", v.StudentMoveView.as_view(), name="student-move"),
    path(
        "students/<str:student_id>/withdraw/",
        v.StudentWithdrawView.as_view(),
        name="student-withdraw",
    ),
    path(
        "students/<str:student_id>/transfer-certificates/",
        v.StudentTransferCertificatesView.as_view(),
        name="student-tcs",
    ),
    path(
        "students/<str:student_id>/transfer-certificates/<str:certificate_id>/document/",
        v.TransferCertificateDocumentView.as_view(),
        name="student-tc-document",
    ),
    path("students/<str:student_id>/id-card/", v.StudentIdCardView.as_view(), name="id-card"),
    path("students/<str:student_id>/invite/", v.StudentInviteView.as_view(), name="student-invite"),
    path("imports/", v.ImportsView.as_view(), name="imports"),
    path("imports/<str:job_id>/", v.ImportDetailView.as_view(), name="import"),
    path("imports/<str:job_id>/apply/", v.ImportApplyView.as_view(), name="import-apply"),
    path("imports/<str:job_id>/report/", v.ImportReportView.as_view(), name="import-report"),
    path("guardians/", v.GuardiansView.as_view(), name="guardians"),
    path("guardians/merge/", v.GuardianMergeView.as_view(), name="guardian-merge"),
    path(
        "guardians/<str:guardian_id>/invite/",
        v.GuardianInviteView.as_view(),
        name="guardian-invite",
    ),
]
