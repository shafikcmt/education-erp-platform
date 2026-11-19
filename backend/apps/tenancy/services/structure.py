"""Organisation profile, institutions and campuses (Phase 3 M8; plan §12.1; ADR-010).

Every function runs inside the tenant request transaction (``tenant_atomic``) and checks the
actor's permission **in the scope of the object**, uncached (defence in depth behind the
view's permission class):

* the profile needs ``tenancy.tenant.update`` at tenant scope;
* creating an institution needs ``tenancy.institution.create`` at tenant scope and capacity
  (``max_institutions``; the registry row is locked for the count, so concurrent creations
  can't exceed it);
* an institution is updated or archived with the permission at that institution's scope;
* campuses need ``tenancy.campus.*`` at the institution's scope (create) or the campus's own
  scope (update, archive); ``max_campuses`` is per tenant.

Archiving keeps the rows (nothing is ever hard-deleted). The first campus of an institution is
its main campus; the main campus can only be archived after another campus became main, or
when it is the last open campus of an archived institution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.services import record
from apps.rbac.engine import ScopeTarget, bump_tenant_version, require_perm
from apps.tenancy.limits import assert_capacity
from apps.tenancy.models import Campus, Institution, Tenant
from apps.tenancy.services import common

if TYPE_CHECKING:
    from django.http import HttpRequest

    from apps.identity.models import User

PROFILE_FIELDS = ("name", "default_locale", "locales", "timezone", "currency", "branding")
INSTITUTION_FIELDS = ("name", "name_i18n", "settings")
CAMPUS_FIELDS = ("name", "name_i18n", "address", "timezone")


def institution_target(institution: Institution) -> ScopeTarget:
    return ScopeTarget(institution.tenant_id, institution.pk)


def campus_target(campus: Campus) -> ScopeTarget:
    return ScopeTarget(campus.tenant_id, campus.institution_id, campus.pk)


def _changed(obj: Any, changes: dict[str, Any], allowed: tuple[str, ...]) -> list[str]:
    fields = []
    for name, value in changes.items():
        if name not in allowed:
            raise ValidationError({name: "This field can't be changed."})
        if getattr(obj, name) != value:
            setattr(obj, name, value)
            fields.append(name)
    return sorted(fields)


# --------------------------------------------------------------------------- profile
@transaction.atomic
def update_profile(
    *, actor: User, changes: dict[str, Any], request: HttpRequest | None = None
) -> Tenant:
    ctx = common.tenant_context()
    require_perm(actor, "tenancy.tenant.update", target=ScopeTarget(ctx.id), use_cache=False)
    tenant = common.lock_tenant(ctx)
    locales = changes.get("locales", tenant.locales)
    default_locale = changes.get("default_locale", tenant.default_locale)
    if locales and default_locale not in locales:
        raise ValidationError({"default_locale": "Must be one of the enabled languages."})
    fields = _changed(tenant, changes, PROFILE_FIELDS)
    if fields:
        tenant.save(update_fields=[*fields, "updated_at"])
        record(
            "tenancy.profile.updated",
            actor=actor,
            request=request,
            target_type="tenant",
            target_id=ctx.id,
            metadata={"fields": ",".join(fields)},
        )
    return tenant


# --------------------------------------------------------------------------- institutions
@transaction.atomic
def create_institution(
    *,
    actor: User,
    code: str,
    name: str,
    institution_type: str,
    name_i18n: dict[str, str] | None = None,
    request: HttpRequest | None = None,
) -> Institution:
    ctx = common.tenant_context()
    require_perm(actor, "tenancy.institution.create", target=ScopeTarget(ctx.id), use_cache=False)
    assert_capacity("institution")  # locks the registry row first (lock order, plan §8.4)
    try:
        with transaction.atomic():
            institution = Institution.objects.create(
                code=code, name=name, institution_type=institution_type, name_i18n=name_i18n or {}
            )
    except IntegrityError:
        raise ValidationError({"code": "An institution with this code already exists."}) from None
    record(
        "tenancy.institution.created",
        actor=actor,
        request=request,
        target_type="tenancy.institution",
        target_id=institution.pk,
        metadata={"object_code": code},
    )
    return institution


@transaction.atomic
def update_institution(
    *,
    actor: User,
    institution: Institution,
    changes: dict[str, Any],
    request: HttpRequest | None = None,
) -> Institution:
    common.tenant_context()
    institution = Institution.objects.select_for_update().get(pk=institution.pk)
    require_perm(
        actor,
        "tenancy.institution.update",
        target=institution_target(institution),
        use_cache=False,
    )
    if institution.archived_at is not None:
        raise ValidationError({"institution": "An archived institution can't be changed."})
    fields = _changed(institution, changes, INSTITUTION_FIELDS)
    if fields:
        institution.save(update_fields=[*fields, "updated_at"])
        record(
            "tenancy.institution.updated",
            actor=actor,
            request=request,
            target_type="tenancy.institution",
            target_id=institution.pk,
            metadata={"fields": ",".join(fields)},
        )
    return institution


@transaction.atomic
def archive_institution(
    *, actor: User, institution: Institution, request: HttpRequest | None = None
) -> Institution:
    """Archive an institution and its open campuses. Role assignments in its scope stop
    applying because the scope objects are archived (assignments are kept for history)."""
    ctx = common.tenant_context()
    common.lock_tenant(ctx)
    institution = Institution.objects.select_for_update().get(pk=institution.pk)
    require_perm(
        actor,
        "tenancy.institution.archive",
        target=institution_target(institution),
        use_cache=False,
    )
    if institution.archived_at is not None:
        return institution
    now = timezone.now()
    institution.archived_at = now
    institution.save(update_fields=["archived_at", "updated_at"])
    Campus.objects.filter(institution=institution, archived_at__isnull=True).update(
        archived_at=now, updated_at=now
    )
    bump_tenant_version(ctx.id)
    record(
        "tenancy.institution.archived",
        actor=actor,
        request=request,
        target_type="tenancy.institution",
        target_id=institution.pk,
    )
    return institution


# --------------------------------------------------------------------------- campuses
@transaction.atomic
def create_campus(
    *,
    actor: User,
    institution: Institution,
    code: str,
    name: str,
    name_i18n: dict[str, str] | None = None,
    address: dict[str, Any] | None = None,
    timezone_name: str = "",
    request: HttpRequest | None = None,
) -> Campus:
    common.tenant_context()
    require_perm(
        actor, "tenancy.campus.create", target=institution_target(institution), use_cache=False
    )
    assert_capacity("campus")
    institution = Institution.objects.select_for_update().get(pk=institution.pk)
    if institution.archived_at is not None:
        raise ValidationError({"institution": "An archived institution can't get campuses."})
    first = not Campus.objects.filter(institution=institution, archived_at__isnull=True).exists()
    if first:  # an archived former main campus gives the flag up
        Campus.objects.filter(institution=institution, is_main=True).update(
            is_main=False, updated_at=timezone.now()
        )
    try:
        with transaction.atomic():
            campus = Campus.objects.create(
                institution=institution,
                code=code,
                name=name,
                name_i18n=name_i18n or {},
                address=address or {},
                timezone=timezone_name,
                is_main=first,
            )
    except IntegrityError:
        raise ValidationError({"code": "A campus with this code already exists."}) from None
    record(
        "tenancy.campus.created",
        actor=actor,
        request=request,
        target_type="tenancy.campus",
        target_id=campus.pk,
        metadata={"object_code": code},
    )
    return campus


@transaction.atomic
def update_campus(
    *,
    actor: User,
    campus: Campus,
    changes: dict[str, Any],
    make_main: bool = False,
    request: HttpRequest | None = None,
) -> Campus:
    common.tenant_context()
    campus = Campus.objects.select_for_update().get(pk=campus.pk)
    require_perm(actor, "tenancy.campus.update", target=campus_target(campus), use_cache=False)
    if campus.archived_at is not None:
        raise ValidationError({"campus": "An archived campus can't be changed."})
    fields = _changed(campus, changes, CAMPUS_FIELDS)
    if make_main and not campus.is_main:
        # Moving "main" changes the institution, so it needs the institution-level permission.
        require_perm(
            actor,
            "tenancy.campus.update",
            target=ScopeTarget(campus.tenant_id, campus.institution_id),
            use_cache=False,
        )
        Campus.objects.filter(institution_id=campus.institution_id, is_main=True).update(
            is_main=False, updated_at=timezone.now()
        )
        campus.is_main = True
        fields.append("is_main")
    if fields:
        campus.save(update_fields=[*fields, "updated_at"])
        record(
            "tenancy.campus.updated",
            actor=actor,
            request=request,
            target_type="tenancy.campus",
            target_id=campus.pk,
            metadata={"fields": ",".join(sorted(fields))},
        )
    return campus


@transaction.atomic
def archive_campus(*, actor: User, campus: Campus, request: HttpRequest | None = None) -> Campus:
    ctx = common.tenant_context()
    common.lock_tenant(ctx)
    campus = Campus.objects.select_for_update().get(pk=campus.pk)
    require_perm(actor, "tenancy.campus.archive", target=campus_target(campus), use_cache=False)
    if campus.archived_at is not None:
        return campus
    others = Campus.objects.filter(
        institution_id=campus.institution_id, archived_at__isnull=True
    ).exclude(pk=campus.pk)
    if campus.is_main and others.exists():
        raise ValidationError(
            {"campus": "Choose another main campus before archiving the main campus."}
        )
    campus.archived_at = timezone.now()
    campus.save(update_fields=["archived_at", "updated_at"])
    bump_tenant_version(ctx.id)
    record(
        "tenancy.campus.archived",
        actor=actor,
        request=request,
        target_type="tenancy.campus",
        target_id=campus.pk,
    )
    return campus
