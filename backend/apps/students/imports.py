"""Bulk import with a dry run, a row-level report and atomic rows (Phase 7 M6; ADR-072,
ADR-074 Q3; plan §7).

Flow:

1. The member uploads the file through ``files`` (purpose ``students.import``: CSV, or XLSX read
   with ``openpyxl`` in read-only mode).
2. :func:`start` checks the kind's permission in the institution, the file (the member's own,
   verified, not infected), the column mapping and the kind's options, then queues a **dry run**.
3. The tenant task ``students.run_import`` reads the file (storage I/O happens in the task body,
   never inside a request's tenant transaction), maps every row and runs it through the same
   services staff use, each row in its own savepoint. A dry run rolls every row back; the report
   has one entry per row with its errors.
4. :func:`apply` queues the real run: every valid row is created in its own savepoint, and the
   report says what was created and what failed (``max_active_students`` and every other rule is
   enforced row by row by the services).

Kinds are pluggable (setting ``STUDENTS_IMPORT_KINDS``): ``students`` (students, the primary
guardian and the enrollment) and ``staff`` (profiles, from ``staff``). Limits: 5 000 rows, and
for XLSX a bounded uncompressed size and compression ratio (zip bombs). The downloadable report
neutralises spreadsheet formulas. Jobs and their files are deleted after 30 days (P28).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import zipfile
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone
from django.utils.module_loading import import_string

from apps.audit.services import record
from apps.core.spreadsheets import safe_cell  # shared with reports (Phase 8 M6)
from apps.core.tenancy import require_tenant
from apps.rbac.engine import ScopeTarget, require_perm
from apps.students.models import ImportJob

if TYPE_CHECKING:
    from apps.identity.models import User

PURPOSE = "students.import"
CSV_TYPE = "text/csv"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_ROWS = 5_000
MAX_COLUMNS = 60
MAX_UNZIPPED = 40 * 1024 * 1024
MAX_RATIO = 100
RETENTION_DAYS = 30


class RowKind(Protocol):
    """A kind of import row (``STUDENTS_IMPORT_KINDS``)."""

    permission: str
    fields: frozenset[str]
    custom_entity: str

    def check_options(self, institution: Any, options: dict[str, Any]) -> dict[str, Any]: ...

    def apply(
        self, actor: Any, institution: Any, values: dict[str, str], options: dict[str, Any]
    ) -> Any: ...


def kinds() -> dict[str, str]:
    return dict(getattr(settings, "STUDENTS_IMPORT_KINDS", {}))


def kind(code: str) -> RowKind:
    path = kinds().get(code)
    if path is None:
        raise ValidationError({"kind": "Unknown import kind."})
    handler: RowKind = import_string(path)()
    return handler


def _authorise(actor: User, handler: RowKind, institution_id: Any) -> None:
    require_perm(
        actor, handler.permission, target=ScopeTarget(require_tenant().id, institution_id),
        use_cache=False,
    )  # fmt: skip


# --------------------------------------------------------------------------- reading files
def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        return value.date().isoformat() if value.time() == dt.time() else value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))  # spreadsheets store 017 as 17.0; phone columns should be text
    return str(value).strip()


def _xlsx_rows(content: bytes) -> list[list[str]]:
    from openpyxl import load_workbook

    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
        unzipped = sum(info.file_size for info in archive.infolist())
    except zipfile.BadZipFile:
        raise ValidationError({"file": "This is not a valid XLSX file."}) from None
    if unzipped > MAX_UNZIPPED or unzipped > MAX_RATIO * max(len(content), 1):
        raise ValidationError({"file": "The spreadsheet is too large once unpacked."})
    try:
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:  # openpyxl raises many types for malformed files
        raise ValidationError({"file": "This XLSX file can't be read."}) from None
    try:
        sheet = book.worksheets[0]
        rows: list[list[str]] = []
        for raw in sheet.iter_rows(values_only=True, max_col=MAX_COLUMNS):
            rows.append([_cell(v) for v in raw])
            if len(rows) > MAX_ROWS + 1:
                break
    finally:
        book.close()
    return rows


def _csv_rows(content: bytes) -> list[list[str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationError({"file": "Save the CSV as UTF-8."}) from None
    rows: list[list[str]] = []
    for raw in csv.reader(io.StringIO(text)):
        rows.append([c.strip() for c in raw[:MAX_COLUMNS]])
        if len(rows) > MAX_ROWS + 1:
            break
    return rows


def parse(content: bytes, content_type: str) -> tuple[list[str], list[dict[str, str]]]:
    """The header and the data rows (as ``{header: value}``), within the limits."""
    rows = _xlsx_rows(content) if content_type == XLSX_TYPE else _csv_rows(content)
    while rows and not any(rows[-1]):
        rows.pop()  # trailing empty lines
    if not rows or not any(rows[0]):
        raise ValidationError({"file": "The file has no header row."})
    header = [h.strip() for h in rows[0]]
    if len({h for h in header if h}) != len([h for h in header if h]):
        raise ValidationError({"file": "Column names must be unique."})
    body = rows[1:]
    if len(body) > MAX_ROWS:
        raise ValidationError({"file": f"At most {MAX_ROWS} rows per file."})
    data = [
        {h: (row[i] if i < len(row) else "") for i, h in enumerate(header) if h} for row in body
    ]
    return header, data


# --------------------------------------------------------------------------- values
def coerce_custom(entity: str, values: dict[str, str]) -> dict[str, Any]:
    """Text cells to the JSON types of the tenant's custom fields (empty cells left out)."""
    from apps.customization.models import FieldDefinition

    types = dict(FieldDefinition.objects.filter(entity=entity).values_list("key", "field_type"))
    out: dict[str, Any] = {}
    for key, raw in values.items():
        if raw == "":
            continue
        kind_ = types.get(key)
        try:
            if kind_ == "number":
                out[key] = int(Decimal(raw))
            elif kind_ == "boolean":
                lowered = raw.lower()
                if lowered not in ("true", "false", "yes", "no", "1", "0"):
                    raise ValueError(raw)
                out[key] = lowered in ("true", "yes", "1")
            elif kind_ == "multi_select":
                out[key] = [part.strip() for part in raw.split(";") if part.strip()]
            else:
                out[key] = raw
        except (ValueError, ArithmeticError):
            raise ValidationError({f"extra.{key}": "Invalid value."}) from None
    return out


def split(values: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """Core values and custom (``extra.<key>``) values of a mapped row."""
    core = {k: v for k, v in values.items() if not k.startswith("extra.")}
    custom = {k[6:]: v for k, v in values.items() if k.startswith("extra.")}
    return core, custom


def _check_mapping(handler: RowKind, mapping: Any) -> dict[str, str]:
    from apps.customization.models import FieldDefinition

    if not isinstance(mapping, dict) or not mapping or len(mapping) > MAX_COLUMNS:
        raise ValidationError({"mapping": "Map the file's columns to fields."})
    custom = set(
        FieldDefinition.objects.filter(
            entity=handler.custom_entity, deprecated_at__isnull=True
        ).values_list("key", flat=True)
    )
    targets: dict[str, str] = {}
    for column, target in mapping.items():
        column, target = str(column).strip(), str(target).strip()
        allowed = target in handler.fields or (target.startswith("extra.") and target[6:] in custom)
        if not column or not allowed:
            raise ValidationError({"mapping": f"Unknown field {target!r}."})
        if target in targets.values():
            raise ValidationError({"mapping": f"{target!r} is mapped twice."})
        targets[column] = target
    if "name" not in targets.values():
        raise ValidationError({"mapping": "Map a column to the name."})
    return targets


# --------------------------------------------------------------------------- jobs
def _file(actor: User, file_id: Any) -> Any:
    from apps.files.models import StoredFile

    row = StoredFile.objects.filter(pk=file_id, purpose=PURPOSE).first()
    if row is None or row.uploaded_by != actor.pk:
        raise ValidationError({"file": "Upload the file for this import first."})
    if row.status != StoredFile.Status.READY or row.scan_state == StoredFile.Scan.INFECTED:
        raise ValidationError({"file": "The file is not ready (still checking, or refused)."})
    return row


def _audit(
    action: str, actor: User, request: HttpRequest | None, job: ImportJob, **meta: Any
) -> None:
    record(action, actor=actor, request=request, target_type="students.importjob",
           target_id=job.pk, metadata=meta)  # fmt: skip


def _queue(job: ImportJob, *, apply: bool) -> None:
    from apps.students.tasks import run_import

    tenant_id, job_id = str(job.tenant_id), str(job.pk)
    transaction.on_commit(lambda: run_import.delay(tenant_id=tenant_id, job_id=job_id, apply=apply))


@transaction.atomic
def start(
    *,
    actor: User,
    institution: Any,
    kind_code: str,
    file_id: Any,
    mapping: Any,
    options: dict[str, Any] | None = None,
    request: HttpRequest | None = None,
) -> ImportJob:
    """Create the job and queue its dry run."""
    handler = kind(kind_code)
    _authorise(actor, handler, institution.pk)
    stored = _file(actor, file_id)
    job = ImportJob.objects.create(
        institution_id=institution.pk, kind=kind_code, file_id=stored.pk,
        mapping=_check_mapping(handler, mapping),
        options=handler.check_options(institution, dict(options or {})), created_by=actor.pk,
    )  # fmt: skip
    _audit("students.import.started", actor, request, job, kind=kind_code)
    _queue(job, apply=False)
    return job


@transaction.atomic
def apply(*, actor: User, job: ImportJob, request: HttpRequest | None = None) -> ImportJob:
    """Queue the real run of a validated job (by the member who applies it)."""
    job = ImportJob.objects.select_for_update().get(pk=job.pk)
    _authorise(actor, kind(job.kind), job.institution_id)
    if job.status != ImportJob.Status.VALIDATED:
        raise ValidationError({"status": "Run the dry run first (or this import already ran)."})
    if job.ok_rows == 0:
        raise ValidationError({"status": "No row passed the dry run."})
    job.status, job.updated_by = ImportJob.Status.APPLYING, actor.pk
    job.save(update_fields=["status", "updated_by", "updated_at"])
    _audit("students.import.applied", actor, request, job, kind=job.kind)
    _queue(job, apply=True)
    return job


class _DryRun(Exception):  # noqa: N818 - control flow: roll the row's savepoint back
    pass


def _errors(exc: Exception) -> dict[str, str]:
    from django.core.exceptions import PermissionDenied

    if isinstance(exc, PermissionDenied):
        return {"row": "You may not do this for this institution."}
    if isinstance(exc, ValidationError) and hasattr(exc, "error_dict"):
        return {k: "; ".join(v) for k, v in exc.message_dict.items()}
    if isinstance(exc, ValidationError):
        return {"row": "; ".join(exc.messages)}
    return {"row": "Unexpected error."}


def run(job_id: Any, *, apply_rows: bool, content: bytes | None = None) -> ImportJob | None:
    """Process the job (called by the task). ``content`` is the file read by the task."""
    from django.core.exceptions import PermissionDenied

    from apps.files.models import StoredFile
    from apps.identity.models import User
    from apps.tenancy.models import Institution

    job = ImportJob.objects.select_for_update().filter(pk=job_id).first()
    expected = ImportJob.Status.APPLYING if apply_rows else ImportJob.Status.VALIDATING
    if job is None or job.status != expected:
        return None
    stored = StoredFile.objects.get(pk=job.file_id)
    actor_id = (job.updated_by if apply_rows else None) or job.created_by
    actor = User.objects.filter(pk=actor_id).first() if actor_id else None
    if actor is None:
        job.status, job.error = ImportJob.Status.FAILED, "The member who ran it is gone."
        job.save()
        return job
    handler = kind(job.kind)
    institution = Institution.objects.get(pk=job.institution_id)
    try:
        if content is None:
            raise ValidationError({"file": "The file could not be read."})
        _, rows = parse(content, stored.content_type)
    except ValidationError as exc:
        job.status, job.error = ImportJob.Status.FAILED, "; ".join(exc.messages)[:300]
        job.finished_at = timezone.now()
        job.save()
        return job
    report: list[dict[str, Any]] = []
    for number, raw in enumerate(rows, start=2):  # line 1 is the header
        values = {job.mapping[c]: v for c, v in raw.items() if c in job.mapping}
        if not any(values.values()):
            continue  # blank line
        entry: dict[str, Any] = {"row": number, "ok": True, "errors": {}, "id": None}
        try:
            with transaction.atomic():
                created = handler.apply(actor, institution, values, job.options)
                if not apply_rows:
                    raise _DryRun
            entry["id"] = str(created) if created is not None else None
        except _DryRun:
            pass
        except (ValidationError, PermissionDenied) as exc:
            entry["ok"], entry["errors"] = False, _errors(exc)
        report.append(entry)
    job.report = report
    job.total_rows = len(report)
    job.ok_rows = sum(1 for e in report if e["ok"])
    job.error_rows = job.total_rows - job.ok_rows
    job.status = ImportJob.Status.APPLIED if apply_rows else ImportJob.Status.VALIDATED
    job.finished_at = timezone.now()
    job.save()
    record(
        "students.import.finished",
        target_type="students.importjob",
        target_id=job.pk,
        metadata={"dry_run": not apply_rows, "ok": job.ok_rows, "failed": job.error_rows},
    )
    return job


def report_csv(job: ImportJob) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["row", "status", "errors", "created_id"])
    for entry in job.report:
        errors = "; ".join(f"{k}: {v}" for k, v in entry.get("errors", {}).items())
        writer.writerow([
            entry["row"], "ok" if entry["ok"] else "error", safe_cell(errors),
            entry.get("id") or "",
        ])  # fmt: skip
    return out.getvalue()


# --------------------------------------------------------------------------- the students kind
STUDENT_FIELDS = frozenset({
    "number", "name", "date_of_birth", "gender", "email", "phone", "guardian_name",
    "guardian_phone", "guardian_email", "guardian_relation", "unit", "roll_number",
})  # fmt: skip


def _year(institution: Any, value: Any) -> Any:
    from apps.academics.models import AcademicYear

    if value in (None, ""):
        return None
    try:
        row = AcademicYear.objects.filter(pk=value, institution_id=institution.pk).first()
    except (ValueError, ValidationError):
        row = None
    if row is None or row.status == AcademicYear.Status.CLOSED:
        raise ValidationError({"options": "Choose an open academic year of this institution."})
    return row


class StudentRows:
    """Students, with the primary guardian and the enrollment (unit code and the job's year)."""

    permission = "students.student.import"
    fields = STUDENT_FIELDS
    custom_entity = "students.student"

    def check_options(self, institution: Any, options: dict[str, Any]) -> dict[str, Any]:
        year = _year(institution, options.get("year"))
        return {"year": str(year.pk)} if year else {}

    def apply(
        self, actor: Any, institution: Any, values: dict[str, str], options: dict[str, Any]
    ) -> Any:
        from apps.academics.models import Unit
        from apps.students import services

        core, custom = split(values)
        person = {k: v for k in ("name", "date_of_birth", "gender", "email", "phone")
                  if (v := core.get(k, ""))}  # fmt: skip
        student = services.create_student(
            actor=actor, institution=institution, values=person,
            extra=coerce_custom(self.custom_entity, custom), number=core.get("number", ""),
        )  # fmt: skip
        guardian = {k: core[f"guardian_{k}"] for k in ("name", "phone", "email")
                    if core.get(f"guardian_{k}")}  # fmt: skip
        if guardian:
            services.link_guardian(
                actor=actor, student=student, values=guardian,
                relation=core.get("guardian_relation") or "guardian", is_primary=True,
            )  # fmt: skip
        if code := core.get("unit"):
            if not options.get("year"):
                raise ValidationError({"unit": "Choose the academic year of the import."})
            unit = Unit.objects.filter(
                institution_id=institution.pk, code=code, archived_at__isnull=True
            ).first()
            if unit is None:
                raise ValidationError({"unit": f"No unit with the code {code!r}."})
            services.enroll(
                actor=actor, student=student, year=options["year"], unit=unit,
                roll_number=core.get("roll_number", ""),
            )  # fmt: skip
        return student.pk
