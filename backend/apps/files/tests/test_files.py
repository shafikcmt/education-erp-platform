"""Files (Phase 6 M3; ADR-064): purposes and limits, quota, presigned uploads bound to a
server-chosen tenant key, verification, scan states, downloads, housekeeping, isolation, API."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.utils import timezone

from apps.core.tenancy import tenant_atomic
from apps.files import services, storage
from apps.files.models import StoredFile
from apps.files.purposes import InvalidPurposeError, Purpose, _purpose
from apps.files.tasks import purge
from tests.helpers import Api, make_user
from tests.isolation.factories import grant_role, seed_tenant_roles, tenant_host

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])
MB = 1024 * 1024
DOC = Purpose("test.document", frozenset({"application/pdf", "image/png"}), 5 * MB, 2, True)


@pytest.fixture(autouse=True)
def purposes(monkeypatch):
    monkeypatch.setattr(services, "declared_purposes", lambda: {DOC.code: DOC})


@pytest.fixture
def objects(monkeypatch):
    """A fake bucket for the network calls (presigning stays real: it's local signing)."""
    bucket: dict[str, dict] = {}
    deleted: list[str] = []
    monkeypatch.setattr(storage, "head", lambda key: bucket.get(key))
    monkeypatch.setattr(storage, "delete", lambda key: deleted.append(key))
    return bucket, deleted


def _upload(org, **kw):
    with tenant_atomic(org.tenant):
        return services.request_upload(
            purpose=kw.pop("purpose", DOC.code),
            name=kw.pop("name", "report.pdf"),
            size=kw.pop("size", 1000),
            content_type=kw.pop("content_type", "application/pdf"),
            **kw,
        )


def test_purposes_are_validated_when_declared():
    with pytest.raises(InvalidPurposeError):
        _purpose("x.html", {"types": ["text/html"], "max_bytes": 10, "max_per_owner": 1})
    with pytest.raises(InvalidPurposeError):
        _purpose("x.big", {"types": ["application/pdf"], "max_bytes": 10**9, "max_per_owner": 1})


def test_uploads_are_bound_to_a_server_key_type_and_size(org):
    row, post = _upload(org, uploaded_by=org.owner.pk)
    assert row.key.startswith(f"tenants/{org.tenant.id}/files/test-document/")
    assert "report" not in row.key  # the client's name never reaches the key
    assert post["fields"]["key"] == row.key and post["fields"]["Content-Type"] == "application/pdf"
    assert "policy" in post["fields"] and row.status == "awaiting_upload"
    for kw in ({"content_type": "text/html"}, {"size": 6 * MB}, {"size": 0}, {"purpose": "nope"}):
        with pytest.raises(ValidationError):
            _upload(org, **kw)


def test_per_owner_count_and_the_storage_quota(org, settings):
    import uuid

    owner = uuid.uuid4()
    _upload(org, owner_type="t", owner_id=owner)
    _upload(org, owner_type="t", owner_id=owner)
    with pytest.raises(ValidationError, match="At most 2"):
        _upload(org, owner_type="t", owner_id=owner)
    settings.STUDIO_QUOTA_DEFAULTS = {**settings.STUDIO_QUOTA_DEFAULTS, "max_storage_mb": 1}
    with pytest.raises(ValidationError, match="storage"):
        _upload(org, size=MB)


def test_confirmed_uploads_are_verified_and_unscanned_files_stay_staff_only(
    org, objects, django_capture_on_commit_callbacks
):
    bucket, deleted = objects
    good, _ = _upload(org, uploaded_by=org.owner.pk)
    bad, _ = _upload(org, uploaded_by=org.owner.pk)
    bucket[good.key] = {"size": 1000, "content_type": "application/pdf"}
    bucket[bad.key] = {"size": 999_999, "content_type": "application/pdf"}  # larger than declared
    with django_capture_on_commit_callbacks(execute=True):
        with tenant_atomic(org.tenant):
            services.confirm_upload(file=good, uploaded_by=org.owner.pk)
            services.confirm_upload(file=bad, uploaded_by=org.owner.pk)
    with tenant_atomic(org.tenant):
        good, bad = StoredFile.objects.get(pk=good.pk), StoredFile.objects.get(pk=bad.pk)
        assert (good.status, good.scan_state, good.size) == ("ready", "unscanned", 1000)
        assert bad.status == "rejected" and deleted == [bad.key]
        url = services.download_url(file=good)
        assert "response-content-disposition=attachment" in url
        with pytest.raises(PermissionDenied):  # applicants only get clean files
            services.download_url(file=good, applicant=True)
        with pytest.raises(ValidationError):
            services.download_url(file=bad)
        with pytest.raises(ValidationError, match="already"):
            services.confirm_upload(file=good)


def test_housekeeping_removes_expired_and_deleted_objects(org, objects):
    _, deleted = objects
    stale, _ = _upload(org)
    gone, _ = _upload(org)
    long_ago = timezone.now() - timedelta(days=2)
    with tenant_atomic(org.tenant):
        StoredFile.objects.filter(pk=stale.pk).update(upload_expires_at=long_ago)
        StoredFile.objects.filter(pk=gone.pk).update(status="deleted", deleted_at=long_ago)
    assert purge.apply(kwargs={"tenant_id": str(org.tenant.id)}).get() == 1
    assert purge.apply(kwargs={"tenant_id": str(org.tenant.id)}).get() == 0  # stale: grace
    assert deleted == [gone.key]
    with tenant_atomic(org.tenant):
        assert StoredFile.objects.get(pk=stale.pk).status == "deleted"
        assert not StoredFile.objects.filter(pk=gone.pk).exists()


def test_files_are_invisible_to_another_tenant(org, tenant_site):
    row, _ = _upload(org)
    other = tenant_site(slug="bravo")
    seed_tenant_roles(other)
    with tenant_atomic(other):
        assert not StoredFile.objects.exists()
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM files_storedfile WHERE id = %s", [row.pk])
            assert cursor.fetchone() == (0,)


def _member(org, email, template, **scope):
    person = make_user(email, mfa=template != "teacher")
    grant_role(org.tenant, person.user, template, **scope)
    api = Api(host=tenant_host(org.tenant))
    api.login(person, expect="authenticated")
    return api, person.user


def test_api_upload_confirm_download_and_who_sees_what(
    org, objects, django_capture_on_commit_callbacks
):
    bucket, _ = objects
    owner, _ = _member(org, "o@example.com", "tenant_owner")
    slot = owner.post(
        "/api/v1/files/uploads/",
        {"purpose": DOC.code, "name": "x.pdf", "size": 10, "content_type": "application/pdf"},
    )
    assert slot.status_code == 201, slot.content
    file_id, key = slot.json()["file"]["id"], slot.json()["fields"]["key"]
    bucket[key] = {"size": 10, "content_type": "application/pdf"}
    with django_capture_on_commit_callbacks(execute=True):
        assert owner.post(f"/api/v1/files/{file_id}/confirm/").status_code == 200
    assert owner.get(f"/api/v1/files/{file_id}/").json()["status"] == "ready"
    download = owner.get(f"/api/v1/files/{file_id}/download/").json()
    assert download["scan_state"] == "unscanned" and download["expires_in"] == 300
    teacher, _ = _member(org, "t@example.com", "teacher", institution=org.north, campus=org.main)
    assert teacher.post("/api/v1/files/uploads/", {"purpose": DOC.code, "name": "x",
                                                   "size": 1, "content_type": "application/pdf"}
                        ).status_code == 403  # fmt: skip
    assert teacher.get(f"/api/v1/files/{file_id}/").status_code == 404
    assert teacher.get(f"/api/v1/files/{file_id}/download/").status_code == 404
    assert owner.delete(f"/api/v1/files/{file_id}/").status_code == 204
    assert owner.get(f"/api/v1/files/{file_id}/").status_code == 404
