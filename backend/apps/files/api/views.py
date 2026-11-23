"""Files API (Phase 6 M3; ADR-064). Tenant host only, module ``files`` (platform).

Members holding ``files.file.upload`` ask for an upload slot (a presigned POST bound to a
server-chosen key, the declared type and size), upload straight to the object storage, then
confirm; a task verifies the object. Downloads are short-lived links for the uploader or for
holders of ``files.file.view``. Files attached to other objects (admissions documents) are
served through those objects' endpoints and permissions.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.tenancy import require_tenant
from apps.files import services, storage
from apps.files.api import serializers as s
from apps.files.models import StoredFile
from apps.identity.api.utils import service_errors
from apps.identity.models import User
from apps.rbac.engine import ScopeTarget, has_perm
from apps.tenancy.api.permissions import HasTenantPermission
from apps.tenancy.api.views_tenant import TenantView

TAGS = ["files"]
OWN = "identity.account.view_own"  # signed-in member; the view checks ownership or the code


def _actor(request: Request) -> User:
    assert isinstance(request.user, User)  # noqa: S101 - permission classes guarantee it
    return request.user


def _file(request: Request, file_id: str) -> Any:
    """The file when the caller uploaded it or holds ``files.file.view`` tenant-wide; else 404."""
    try:
        row = StoredFile.objects.filter(pk=file_id).first()
    except (ValueError, ValidationError):
        row = None
    user = _actor(request)
    if row is None or row.status == StoredFile.Status.DELETED:
        raise NotFound()
    if row.uploaded_by == user.pk:
        return row
    if has_perm(user, "files.file.view", target=ScopeTarget(require_tenant().id), use_cache=False):
        return row
    raise NotFound()


class FilesView(TenantView):
    module_code = "files"


class UploadsView(FilesView):
    permission_classes = [HasTenantPermission({"POST": "files.file.upload"})]

    @extend_schema(
        tags=TAGS,
        summary="Ask for an upload slot (presigned POST)",
        request=s.UploadRequestSerializer,
        responses={201: s.UploadSlotSerializer},
    )
    def post(self, request: Request) -> Response:
        form = s.UploadRequestSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        with service_errors():
            row, post = services.request_upload(
                uploaded_by=_actor(request).pk, request=request._request, **form.validated_data
            )
        data = {"file": row, "url": post["url"], "fields": post["fields"]}
        return Response(s.UploadSlotSerializer(data).data, status=status.HTTP_201_CREATED)


class ConfirmView(FilesView):
    permission_classes = [HasTenantPermission({"POST": "files.file.upload"})]

    @extend_schema(
        tags=TAGS,
        summary="Confirm an upload (the object is then verified)",
        request=None,
        responses=s.StoredFileSerializer,
    )
    def post(self, request: Request, file_id: str) -> Response:
        row = _file(request, file_id)
        with service_errors():
            row = services.confirm_upload(file=row, uploaded_by=_actor(request).pk)
        return Response(s.StoredFileSerializer(row).data)


class FileDetailView(FilesView):
    permission_classes = [HasTenantPermission({"GET": OWN, "DELETE": OWN})]

    @extend_schema(tags=TAGS, summary="A file's state", responses=s.StoredFileSerializer)
    def get(self, request: Request, file_id: str) -> Response:
        return Response(s.StoredFileSerializer(_file(request, file_id)).data)

    @extend_schema(tags=TAGS, summary="Delete my upload", responses={204: None})
    def delete(self, request: Request, file_id: str) -> Response:
        row = _file(request, file_id)
        if row.uploaded_by != _actor(request).pk:
            raise NotFound()  # only the uploader deletes through this endpoint
        services.delete_file(file=row, actor_id=_actor(request).pk, request=request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DownloadView(FilesView):
    permission_classes = [HasTenantPermission({"GET": OWN})]

    @extend_schema(tags=TAGS, summary="A short-lived download link", responses=s.DownloadSerializer)
    def get(self, request: Request, file_id: str) -> Response:
        row = _file(request, file_id)
        with service_errors():
            url = services.download_url(file=row)
        data = {"url": url, "scan_state": row.scan_state, "expires_in": storage.DOWNLOAD_SECONDS}
        return Response(s.DownloadSerializer(data).data)
