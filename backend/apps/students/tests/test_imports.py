"""Bulk import (Phase 7 M6; ADR-072, ADR-074 Q3): CSV and XLSX parsing within limits, the
mapping, the dry run (nothing written), the apply (each row atomic, with a report), the staff
kind, permissions, step-up at the API, the formula-safe report and P28 housekeeping."""

from __future__ import annotations

import datetime as dt
import io
from typing import Any

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.academics import services as academics
from apps.core.tenancy import tenant_atomic
from apps.customization import fields, numbering
from apps.files import storage
from apps.files.models import StoredFile
from apps.module_registry import services as registry_services
from apps.staff import services as staff_services
from apps.staff.models import StaffProfile
from apps.students import imports
from apps.students.models import Enrollment, ImportJob, Student, StudentGuardian
from apps.students.tasks import purge_imports
from apps.tenancy.models import Institution
from tests.helpers import Api, make_user
from tests.isolation.factories import grant_role, tenant_host

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])
V1 = "/api/v1"
CSV = (
    "﻿Name,Phone,Guardian,Guardian phone,Class,Roll,Blood,Born\n"
    "Ana,01711000001,Rina,01711000009,6A,1,O+,2015-02-01\n"
    "Bo,,Rina,01711000009,6A,2,A+,not-a-date\n"
    "Cy,,,,9Z,3,,\n"
    ",,,,,,,\n"
    "Di,,Karim,01811000000,6A,4,B+,2015-03-01\n"
)
MAPPING = {"Name": "name", "Phone": "phone", "Guardian": "guardian_name",
           "Guardian phone": "guardian_phone", "Class": "unit", "Roll": "roll_number",
           "Blood": "extra.blood_group", "Born": "date_of_birth"}  # fmt: skip


@pytest.fixture
def owner(org):
    user = make_user("import-owner@example.com", mfa=True).user
    grant_role(org.tenant, user, "tenant_owner")
    return user


@pytest.fixture(autouse=True)
def modules(org, admin):
    for module in ("academics", "students", "staff"):
        registry_services.set_override(
            actor=admin.user, tenant_id=org.tenant.id, module_code=module, kind="grant",
            reason="Pilot agreement for imports",
        )  # fmt: skip


@pytest.fixture
def bucket(monkeypatch):
    """Object contents by key (the storage is not reached in tests)."""
    objects: dict[str, bytes] = {}
    monkeypatch.setattr(storage, "read", lambda key, max_bytes: objects[key])
    return objects


@pytest.fixture
def school(org, owner):
    with tenant_atomic(org.tenant):
        Institution.objects.filter(pk=org.north.pk).update(
            preset_code="school.general.v2", preset_version="2"
        )
        year = academics.create_year(
            actor=owner, institution=org.north, code="2027", name="2027",
            start_date=dt.date(2027, 1, 1), end_date=dt.date(2027, 12, 31),
        )  # fmt: skip
        six = academics.create_unit(
            actor=owner, institution=org.north, level_key="class", code="6", name="Six"
        )
        academics.create_unit(
            actor=owner, institution=org.north, level_key="section", code="6A", name="A",
            parent=six,
        )  # fmt: skip
        numbering.define_sequence(
            actor=owner, key="student", name="Students", pattern="STU-{SEQ:4}",
            scope="institution", reset="never",
        )  # fmt: skip
        fields.define_field(
            actor=owner, entity="students.student", key="blood_group", field_type="text",
            labels={"en": "Blood group"},
        )  # fmt: skip
    return {"year": year}


def _upload(org, bucket, user, content: bytes, content_type: str = imports.CSV_TYPE) -> Any:
    with tenant_atomic(org.tenant):
        row = StoredFile.objects.create(
            purpose=imports.PURPOSE, key=f"t/{len(bucket)}", original_name="x.csv",
            content_type=content_type, declared_size=len(content), size=len(content),
            status="ready", scan_state="unscanned", uploaded_by=user.pk,
            upload_expires_at=timezone.now(),
        )  # fmt: skip
    bucket[row.key] = content
    return row


def _xlsx(rows: list[list[Any]]) -> bytes:
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def test_parsing_csv_and_xlsx_within_limits():
    header, rows = imports.parse(CSV.encode(), imports.CSV_TYPE)
    assert header[0] == "Name" and rows[0]["Guardian phone"] == "01711000009" and len(rows) == 5
    sheet = _xlsx([["Name", "Phone", "Born"], ["Ana", 1711000001.0, dt.datetime(2015, 2, 1)]])
    _, xrows = imports.parse(sheet, imports.XLSX_TYPE)
    assert xrows == [{"Name": "Ana", "Phone": "1711000001", "Born": "2015-02-01"}]
    with pytest.raises(ValidationError, match="unique"):
        imports.parse(b"A,A\n1,2\n", imports.CSV_TYPE)
    with pytest.raises(ValidationError, match="5000 rows"):
        imports.parse(("N\n" + "x\n" * 5001).encode(), imports.CSV_TYPE)
    with pytest.raises(ValidationError, match="UTF-8"):
        imports.parse("Name\nÄna\n".encode("latin-1"), imports.CSV_TYPE)
    with pytest.raises(ValidationError, match="not a valid XLSX"):
        imports.parse(b"PK-not-a-zip", imports.XLSX_TYPE)
    assert imports.safe_cell("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert imports.safe_cell("+1") == "'+1" and imports.safe_cell("Ana") == "Ana"


def test_dry_run_writes_nothing_and_apply_creates_valid_rows(
    org, owner, school, bucket, django_capture_on_commit_callbacks
):
    stored = _upload(org, bucket, owner, CSV.encode())
    with django_capture_on_commit_callbacks(execute=True), tenant_atomic(org.tenant):
        job = imports.start(
            actor=owner, institution=org.north, kind_code="students", file_id=stored.pk,
            mapping=MAPPING, options={"year": str(school["year"].pk)},
        )  # fmt: skip
    with tenant_atomic(org.tenant):
        job = ImportJob.objects.get(pk=job.pk)
        assert (job.status, job.total_rows, job.ok_rows, job.error_rows) == ("validated", 4, 2, 2)
        failed = {e["row"]: e["errors"] for e in job.report if not e["ok"]}
        assert set(failed) == {3, 4}  # a bad date; an unknown unit (the blank line is skipped)
        assert "date_of_birth" in failed[3] and "unit" in failed[4]
        assert not Student.objects.exists()  # the dry run rolled every row back
    with django_capture_on_commit_callbacks(execute=True), tenant_atomic(org.tenant):
        imports.apply(actor=owner, job=job)
    with tenant_atomic(org.tenant):
        job = ImportJob.objects.get(pk=job.pk)
        assert (job.status, job.ok_rows, job.error_rows) == ("applied", 2, 2)
        created = {e["id"] for e in job.report if e["ok"]}
        names = dict(Student.objects.filter(pk__in=created).values_list("name", "extra"))
        assert names == {"Ana": {"blood_group": "O+"}, "Di": {"blood_group": "B+"}}
        assert Enrollment.objects.filter(student__name__in=["Ana", "Di"]).count() == 2
        assert StudentGuardian.objects.filter(is_primary=True).count() == 2
        with pytest.raises(ValidationError, match="already ran"):
            imports.apply(actor=owner, job=job)
        report = imports.report_csv(job)
        assert report.splitlines()[0] == "row,status,errors,created_id" and "error" in report


def test_mapping_files_and_permissions_are_checked(org, owner, school, bucket):
    stored = _upload(org, bucket, owner, CSV.encode())
    other = make_user("other-importer@example.com", mfa=True).user
    grant_role(org.tenant, other, "institution_admin", institution=org.north)
    with tenant_atomic(org.tenant):
        for bad, message in (({"Name": "nickname"}, "Unknown field"),
                             ({"Phone": "phone"}, "name"),
                             ({"Name": "name", "Guardian": "name"}, "mapped twice")):  # fmt: skip
            with pytest.raises(ValidationError, match=message):
                imports.start(actor=owner, institution=org.north, kind_code="students",
                              file_id=stored.pk, mapping=bad)  # fmt: skip
        with pytest.raises(ValidationError, match="Unknown import kind"):
            imports.start(actor=owner, institution=org.north, kind_code="fees",
                          file_id=stored.pk, mapping=MAPPING)  # fmt: skip
        with pytest.raises(ValidationError, match="Upload the file"):  # not their upload
            imports.start(actor=other, institution=org.north, kind_code="students",
                          file_id=stored.pk, mapping=MAPPING)  # fmt: skip
    with tenant_atomic(org.tenant), pytest.raises(PermissionDenied):
        imports.start(actor=org.teacher, institution=org.north, kind_code="students",
                      file_id=stored.pk, mapping=MAPPING)  # fmt: skip


def test_the_staff_kind(org, owner, bucket, django_capture_on_commit_callbacks):
    with tenant_atomic(org.tenant):
        staff_services.create_department(
            actor=owner, institution=org.north, code="SCI", name="Science"
        )
    content = _xlsx([["Name", "No", "Dept"], ["Rahim", "T-1", "SCI"], ["Nila", "T-2", "ART"]])
    stored = _upload(org, bucket, owner, content, imports.XLSX_TYPE)
    with django_capture_on_commit_callbacks(execute=True), tenant_atomic(org.tenant):
        job = imports.start(
            actor=owner, institution=org.north, kind_code="staff", file_id=stored.pk,
            mapping={"Name": "name", "No": "number", "Dept": "department"},
        )  # fmt: skip
    with django_capture_on_commit_callbacks(execute=True), tenant_atomic(org.tenant):
        imports.apply(actor=owner, job=ImportJob.objects.get(pk=job.pk))
    with tenant_atomic(org.tenant):
        job = ImportJob.objects.get(pk=job.pk)
        assert (job.ok_rows, job.error_rows) == (1, 1)
        assert list(StaffProfile.objects.values_list("name", flat=True)) == ["Rahim"]


def test_the_import_api_needs_step_up_and_hides_other_institutions(
    org, admin, school, bucket, django_capture_on_commit_callbacks
):
    head = make_user("import-head@example.com", mfa=True)
    grant_role(org.tenant, head.user, "institution_admin", institution=org.north)
    stored = _upload(org, bucket, head.user, CSV.encode())
    api = Api(host=tenant_host(org.tenant))
    api.login(head, expect="authenticated")
    body = {"institution": str(org.north.pk), "kind": "students", "file": str(stored.pk),
            "mapping": MAPPING, "options": {"year": str(school["year"].pk)}}  # fmt: skip
    assert api.post(f"{V1}/imports/", body).status_code == 403  # import needs a fresh step-up
    api.step_up(head)
    with django_capture_on_commit_callbacks(execute=True):
        started = api.post(f"{V1}/imports/", body)
    assert started.status_code == 201, started.content
    job_id = started.json()["id"]
    detail = api.get(f"{V1}/imports/{job_id}/").json()
    assert (detail["status"], detail["ok_rows"], len(detail["report"])) == ("validated", 2, 4), (
        detail["report"]
    )
    with django_capture_on_commit_callbacks(execute=True):
        applied = api.post(f"{V1}/imports/{job_id}/apply/", {})
    assert applied.status_code == 200, applied.content
    report = api.get(f"{V1}/imports/{job_id}/report/")
    assert report.status_code == 200 and report["Content-Type"].startswith("text/csv")
    assert [j["id"] for j in api.get(f"{V1}/imports/").json()] == [job_id]
    south = make_user("import-south@example.com", mfa=True)
    grant_role(org.tenant, south.user, "institution_admin", institution=org.south)
    other = Api(host=tenant_host(org.tenant))
    other.login(south, expect="authenticated")
    other.step_up(south)
    assert other.get(f"{V1}/imports/{job_id}/").status_code == 404
    assert other.post(f"{V1}/imports/{job_id}/apply/", {}).status_code == 404


def test_p28_deletes_old_jobs_and_their_files(org, owner, school, bucket):
    stored = _upload(org, bucket, owner, CSV.encode())
    with tenant_atomic(org.tenant):
        job = ImportJob.objects.create(
            institution_id=org.north.pk, kind="students", file_id=stored.pk, mapping=MAPPING,
            status="validated", created_by=owner.pk,
        )  # fmt: skip
        ImportJob.objects.filter(pk=job.pk).update(
            created_at=timezone.now() - dt.timedelta(days=imports.RETENTION_DAYS + 1)
        )
    assert purge_imports.delay(tenant_id=str(org.tenant.id)).get() == 1
    with tenant_atomic(org.tenant):
        assert not ImportJob.objects.exists()
        assert StoredFile.objects.get(pk=stored.pk).status == "deleted"
