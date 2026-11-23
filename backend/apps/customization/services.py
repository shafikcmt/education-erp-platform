"""Configuration drafts, publishing and rollback (Phase 5 M1; ADR-057).

Every function runs inside the current tenant's transaction (``tenant_atomic``), checks the
permission in the exact scope (uncached), validates the document against the declared keys,
serialises changes of one scope with a transaction-scoped advisory lock and writes an audit
event with a diff of the keys. Published versions are never changed: publishing archives the
previous one; a rollback publishes a copy of an older version as a new version.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models import Max, QuerySet
from django.utils import timezone
from django.utils.module_loading import import_string

from apps.audit.services import record
from apps.core.tenancy import require_tenant
from apps.customization.models import ConfigVersion
from apps.customization.registry import declared_settings
from apps.customization.resolver import invalidate
from apps.customization.scopes import ConfigScope
from apps.rbac.engine import require_perm

if TYPE_CHECKING:
    from django.http import HttpRequest

    from apps.identity.models import User

EDIT, PUBLISH = "customization.config.edit", "customization.config.publish"
MAX_DOCUMENT_BYTES = 64 * 1024


def _lock(scope: ConfigScope) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            [f"config:{require_tenant().id}:{scope.cache_part()}"],
        )


def _check_scope_exists(scope: ConfigScope) -> None:
    from apps.tenancy.models import Campus, Institution

    if (
        scope.institution_id is not None
        and not Institution.objects.filter(
            pk=scope.institution_id, archived_at__isnull=True
        ).exists()
    ):
        raise ValidationError({"scope": "Unknown institution."})
    if (
        scope.campus_id is not None
        and scope.institution_id is not None
        and not Campus.objects.filter(
            pk=scope.campus_id, institution_id=scope.institution_id, archived_at__isnull=True
        ).exists()
    ):
        raise ValidationError({"scope": "Unknown campus of this institution."})


def validate_document(scope: ConfigScope, data: Any) -> dict[str, Any]:
    """Declared keys only, allowed in this scope, each valid against its schema."""
    if not isinstance(data, dict):
        raise ValidationError({"data": "The configuration is an object of declared keys."})
    if len(json.dumps(data, ensure_ascii=False).encode()) > MAX_DOCUMENT_BYTES:
        raise ValidationError({"data": "The configuration is too large."})
    specs = declared_settings()
    errors: dict[str, str] = {}
    for key, value in data.items():
        spec = specs.get(key)
        if spec is None:
            errors[key] = "Unknown setting."
        elif scope.kind not in spec.scopes:
            errors[key] = f"This setting can't be set for a {scope.kind}."
        else:
            first = next(iter(spec.validator().iter_errors(value)), None)
            if first is not None:
                where = "/".join(str(p) for p in first.absolute_path)
                errors[key] = f"Invalid value{f' at {where}' if where else ''}: {first.message}"
    if errors:
        raise ValidationError(errors)
    return dict(data)


def diff(old: dict[str, Any], new: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "added": sorted(set(new) - set(old)),
        "removed": sorted(set(old) - set(new)),
        "changed": sorted(k for k in set(old) & set(new) if old[k] != new[k]),
    }


def _rows(scope: ConfigScope) -> QuerySet[ConfigVersion]:
    return ConfigVersion.objects.filter(**scope.filters())


def _published(scope: ConfigScope) -> ConfigVersion | None:
    return _rows(scope).filter(status=ConfigVersion.Status.PUBLISHED).first()


def _next_number(scope: ConfigScope) -> int:
    return int(_rows(scope).aggregate(n=Max("number"))["n"] or 0) + 1


def _audit(
    action: str,
    actor: User,
    request: HttpRequest | None,
    scope: ConfigScope,
    version: ConfigVersion,
    **metadata: Any,
) -> None:
    record(
        action,
        actor=actor,
        request=request,
        target_type="customization.config",
        target_id=version.pk,
        metadata={"scope": scope.kind, "number": version.number, **metadata},
    )


def save_draft(
    *,
    actor: User,
    scope: ConfigScope,
    data: dict[str, Any],
    note: str = "",
    request: HttpRequest | None = None,
) -> ConfigVersion:
    """Replace the scope's draft with ``data`` (the full document of this scope)."""
    require_perm(actor, EDIT, target=scope.target(), use_cache=False)
    _check_scope_exists(scope)
    cleaned = validate_document(scope, data)
    _lock(scope)
    draft = _rows(scope).filter(status=ConfigVersion.Status.DRAFT).first()
    before = draft.data if draft else (getattr(_published(scope), "data", None) or {})
    if draft is None:
        draft = ConfigVersion(
            scope_type=scope.kind,
            institution_id=scope.institution_id,
            campus_id=scope.campus_id,
            number=_next_number(scope),
            created_by=actor.pk,
        )
    draft.data, draft.note, draft.updated_by = cleaned, note[:200], actor.pk
    draft.save()
    _audit(
        "customization.config.draft_saved", actor, request, scope, draft, **diff(before, cleaned)
    )
    return draft


def discard_draft(*, actor: User, scope: ConfigScope, request: HttpRequest | None = None) -> bool:
    require_perm(actor, EDIT, target=scope.target(), use_cache=False)
    _lock(scope)
    draft = _rows(scope).filter(status=ConfigVersion.Status.DRAFT).first()
    if draft is None:
        return False
    _audit("customization.config.draft_discarded", actor, request, scope, draft)
    draft.delete()
    return True


def _activate(
    actor: User, scope: ConfigScope, version: ConfigVersion
) -> tuple[ConfigVersion | None, dict[str, Any]]:
    current = _published(scope)
    before = current.data if current else {}
    if current is not None:
        current.status = ConfigVersion.Status.ARCHIVED
        current.save(update_fields=["status", "updated_at"])
    version.status = ConfigVersion.Status.PUBLISHED
    version.published_at, version.published_by = timezone.now(), actor.pk
    version.save()
    invalidate()
    # Modules veto configurations their data can't live with (e.g. structure levels in use);
    # a refusal raises inside this transaction, so the publish is undone.
    for path in getattr(settings, "CUSTOMIZATION_PUBLISH_CHECKS", []):
        import_string(path)(scope)
    return current, before


def publish(
    *,
    actor: User,
    scope: ConfigScope,
    note: str = "",
    request: HttpRequest | None = None,
) -> ConfigVersion:
    require_perm(actor, PUBLISH, target=scope.target(), use_cache=False)
    _check_scope_exists(scope)
    _lock(scope)
    draft = _rows(scope).filter(status=ConfigVersion.Status.DRAFT).first()
    if draft is None:
        raise ValidationError({"draft": "There is no draft to publish."})
    validate_document(scope, draft.data)  # keys or schemas may have changed since the save
    if note:
        draft.note = note[:200]
    _, before = _activate(actor, scope, draft)
    _audit(
        "customization.config.published", actor, request, scope, draft, **diff(before, draft.data)
    )
    return draft


def rollback(
    *,
    actor: User,
    scope: ConfigScope,
    number: int,
    note: str = "",
    request: HttpRequest | None = None,
) -> ConfigVersion:
    """Publish a copy of version ``number`` as a new version (history is never rewritten)."""
    require_perm(actor, PUBLISH, target=scope.target(), use_cache=False)
    _check_scope_exists(scope)
    _lock(scope)
    source = (
        _rows(scope)
        .filter(
            number=number,
            status__in=(ConfigVersion.Status.PUBLISHED, ConfigVersion.Status.ARCHIVED),
        )
        .first()
    )
    if source is None:
        raise ValidationError({"number": "Unknown published or archived version."})
    cleaned = validate_document(scope, source.data)
    copy = ConfigVersion(
        scope_type=scope.kind,
        institution_id=scope.institution_id,
        campus_id=scope.campus_id,
        number=_next_number(scope),
        data=cleaned,
        note=(note or f"Rollback to version {number}")[:200],
        based_on=number,
        created_by=actor.pk,
    )
    _, before = _activate(actor, scope, copy)
    _audit(
        "customization.config.rolled_back",
        actor,
        request,
        scope,
        copy,
        source=number,
        **diff(before, cleaned),
    )
    return copy
