"""Files routes (Phase 6 M3). Tenant host only."""

from django.urls import path

from apps.files.api import views as v

app_name = "files"

urlpatterns = [
    path("files/uploads/", v.UploadsView.as_view(), name="uploads"),
    path("files/<str:file_id>/", v.FileDetailView.as_view(), name="file"),
    path("files/<str:file_id>/confirm/", v.ConfirmView.as_view(), name="confirm"),
    path("files/<str:file_id>/download/", v.DownloadView.as_view(), name="download"),
]
