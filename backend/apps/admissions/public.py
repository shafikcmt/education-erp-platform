"""Public admissions on tenant hosts (Phase 6 M5; ADR-065).

Anonymous by design, so every step is enumeration-safe and throttled:

1. ``submit_public`` validates the application with the cycle's form, stores a **draft** and
   emails a single-use verification link (48 hours). A per-IP limit answers 429; the per-email
   limit (per cycle) and the honeypot are silent; the answer is the same either way.
2. ``verify_public`` turns the draft into a submitted application (number allocated) and emails
   a **status link**. Only SHA-256 hashes of both tokens are stored; tokens travel in the URL
   fragment.
3. With the status link the applicant sees the status, answers an offer and adds documents
   (purpose ``admissions.document``) while the application is in review.

There are no applicant accounts (ADR-066 Q6). The cycle's workflow starts when staff take a
public application into review (a public submitter is no member who could start it).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.admissions import services
from apps.admissions.models import Application, Cycle
from apps.audit.services import record
from apps.core.net import client_ip
from apps.core.tokens import generate_token, hash_token
from apps.identity import throttling
from apps.identity.errors import RateLimited

DRAFT_HOURS = 48
DOCUMENTS = "admissions.document"
_INVALID = "This link is invalid or has expired."
_ANSWER_STATUSES = (Application.Status.SUBMITTED, Application.Status.UNDER_REVIEW,
                    Application.Status.TEST_SCHEDULED, Application.Status.EVALUATED)  # fmt: skip


def _throttle(request: HttpRequest | None, bucket_name: str) -> None:
    bucket = throttling.Bucket.named(bucket_name)
    subject = throttling.subject_key("ip", (client_ip(request) if request else "") or "unknown")
    if bucket.hit(subject) > bucket.limit:
        raise RateLimited(bucket.retry_after(subject))


def open_cycles(today: dt.date | None = None) -> list[Cycle]:
    today = today or dt.date.today()
    return list(
        Cycle.objects.filter(status=Cycle.Status.OPEN, opens_on__lte=today, closes_on__gte=today)
        .prefetch_related("targets")
        .order_by("closes_on")
    )


def open_cycle(cycle_id: Any) -> Cycle:
    cycle = next((c for c in open_cycles() if str(c.pk) == str(cycle_id)), None)
    if cycle is None:
        raise ValidationError({"cycle": "This admission is not open."})
    return cycle


def _email(application: Application, template: str, page: str, token: str, locale: str) -> None:
    from apps.identity.services.notifications import send_security_email
    from apps.tenancy.models import Tenant
    from apps.tenancy.services.invitations import tenant_link

    link = tenant_link(locale, page, token)
    to, name = application.applicant_email, Tenant.objects.get(pk=application.tenant_id).name

    def deliver() -> None:
        send_security_email(
            template, to=to, user=None, locale=locale,
            context={"tenant_name": name, "action_url": link, "hours": DRAFT_HOURS},
        )  # fmt: skip

    transaction.on_commit(deliver)


@transaction.atomic
def submit_public(
    request: HttpRequest | None,
    *,
    cycle_id: Any,
    target: Any,
    values: dict[str, Any],
    website: str = "",
    locale: str = "en",
) -> None:
    _throttle(request, "admission_ip")
    if website:
        return  # honeypot: bots fill every field
    cycle = open_cycle(cycle_id)
    target_row = services._target(cycle, target)
    core, custom = services._split(cycle, values)
    email = str(core.get("applicant_email") or "").strip().lower()
    if not email:
        raise ValidationError({"applicant_email": "An email address is needed to confirm."})
    bucket = throttling.Bucket.named("admission_email")
    if bucket.hit(throttling.subject_key("email", f"{cycle.pk}:{email}")) > bucket.limit:
        return  # silent: the answer is the same
    raw, digest = generate_token()
    application = Application.objects.create(
        institution_id=cycle.institution_id,
        cycle=cycle,
        target=target_row,
        source=Application.Source.PUBLIC,
        status=Application.Status.DRAFT,
        extra=custom,
        core={k: v for k, v in core.items() if k not in services.PROMOTED},
        applicant_name=core["applicant_name"],
        applicant_email=email,
        applicant_phone=str(core.get("applicant_phone") or ""),
        date_of_birth=core.get("date_of_birth"),
        verify_token_hash=digest,
        verify_expires_at=timezone.now() + dt.timedelta(hours=DRAFT_HOURS),
    )
    record(
        "admissions.application.drafted",
        request=request,
        target_type="admissions.application",
        target_id=application.pk,
        metadata={"source": "public"},
    )
    _email(application, "admission_verify", "apply/verify", raw, locale)


@transaction.atomic
def verify_public(request: HttpRequest | None, token: str, *, locale: str = "en") -> None:
    _throttle(request, "admission_verify_ip")
    application = (
        Application.objects.select_for_update()
        .filter(
            verify_token_hash=hash_token(token or ""),
            status=Application.Status.DRAFT,
            verify_expires_at__gt=timezone.now(),
        )
        .first()
    )
    if application is None:
        raise ValidationError({"token": _INVALID})
    raw, digest = generate_token()
    application.email_verified_at = timezone.now()
    application.verify_token_hash, application.status_token_hash = "", digest
    application = services.submit(application, actor=None)
    record(
        "admissions.application.submitted",
        request=request,
        target_type="admissions.application",
        target_id=application.pk,
        metadata={"source": "public"},
    )
    _email(application, "admission_status", "apply/status", raw, locale)


def by_status_token(token: str) -> Application:
    application = (
        Application.objects.filter(status_token_hash=hash_token(token or ""))
        .exclude(status_token_hash="")
        .first()
    )
    if application is None:
        raise ValidationError({"token": _INVALID})
    return application


def status_of(token: str) -> dict[str, Any]:
    from apps.files.models import StoredFile

    application = by_status_token(token)
    cycle = Cycle.objects.get(pk=application.cycle_id)
    documents = StoredFile.objects.filter(
        owner_type="admissions.application",
        owner_id=application.pk,
        status__in=(StoredFile.Status.VERIFYING, StoredFile.Status.READY),
    ).order_by("created_at")
    return {
        "number": application.number,
        "status": application.status,
        "cycle": cycle.name,
        "applicant_name": application.applicant_name,
        "decision_note": application.decision_note
        if application.status in (Application.Status.OFFERED, Application.Status.REJECTED)
        else "",
        "can_add_documents": application.status in _ANSWER_STATUSES,
        "documents": [
            {"id": str(d.pk), "name": d.original_name, "status": d.status} for d in documents
        ],
    }


@transaction.atomic
def respond_public(request: HttpRequest | None, token: str, *, accept: bool) -> Application:
    _throttle(request, "admission_verify_ip")
    application = by_status_token(token)
    return services.respond_to_offer(application, accept=accept, actor=None, request=request)


@transaction.atomic
def document_slot(
    request: HttpRequest | None, token: str, *, name: str, size: int, content_type: str
) -> tuple[Any, dict[str, Any]]:
    from apps.files.services import request_upload

    _throttle(request, "admission_verify_ip")
    application = by_status_token(token)
    if application.status not in _ANSWER_STATUSES:
        raise ValidationError(
            {"status": "Documents can be added while the application is in review."}
        )
    return request_upload(
        purpose=DOCUMENTS,
        name=name,
        size=size,
        content_type=content_type,
        owner_type="admissions.application",
        owner_id=application.pk,
        request=request,
    )


@transaction.atomic
def confirm_document(request: HttpRequest | None, token: str, file_id: Any) -> Any:
    from apps.files.models import StoredFile
    from apps.files.services import confirm_upload

    application = by_status_token(token)
    row = StoredFile.objects.filter(
        pk=file_id, owner_type="admissions.application", owner_id=application.pk
    ).first()
    if row is None:
        raise ValidationError({"file": "Unknown document."})
    return confirm_upload(file=row)


def purge_drafts(now: dt.datetime | None = None) -> int:
    """Unverified public drafts past their expiry are deleted (they hold personal data)."""
    now = now or timezone.now()
    deleted, _ = Application.objects.filter(
        status=Application.Status.DRAFT,
        source=Application.Source.PUBLIC,
        verify_expires_at__lt=now,
    ).delete()
    return deleted


def close_past_cycles(today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    return Cycle.objects.filter(status=Cycle.Status.OPEN, closes_on__lt=today).update(
        status=Cycle.Status.CLOSED
    )
