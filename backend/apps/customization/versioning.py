"""Draft / publish lifecycle shared by versioned Studio artefacts (Phase 5 M3-M5).

Rules, forms and workflows keep one row per version of a ``key``: at most one draft and one
published version (database constraints). Publishing archives the previous version; published
rows are never edited. Callers check permissions and validate content first.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Max, Model
from django.utils import timezone

from apps.customization.models import Lifecycle


def draft_for[M: Model](model: type[M], key: str, actor_id: Any) -> M:
    """The key's draft, or a new unsaved one numbered after the latest version."""
    draft = model.objects.select_for_update().filter(key=key, status=Lifecycle.DRAFT).first()  # type: ignore[attr-defined]
    if draft is not None:
        return draft  # type: ignore[no-any-return]
    latest = model.objects.filter(key=key).aggregate(n=Max("number"))["n"] or 0  # type: ignore[attr-defined]
    return model(key=key, number=int(latest) + 1, created_by=actor_id)


def published[M: Model](model: type[M], key: str) -> M | None:
    return model.objects.filter(key=key, status=Lifecycle.PUBLISHED).first()  # type: ignore[attr-defined, no-any-return]


def draft_or_none[M: Model](model: type[M], key: str) -> M | None:
    return model.objects.select_for_update().filter(key=key, status=Lifecycle.DRAFT).first()  # type: ignore[attr-defined, no-any-return]


def activate[M: Model](model: type[M], draft: M, actor_id: Any) -> M:
    now = timezone.now()
    model.objects.filter(key=draft.key, status=Lifecycle.PUBLISHED).update(  # type: ignore[attr-defined]
        status=Lifecycle.ARCHIVED, updated_at=now
    )
    draft.status, draft.published_at, draft.published_by = Lifecycle.PUBLISHED, now, actor_id  # type: ignore[attr-defined]
    draft.save(update_fields=["status", "published_at", "published_by", "updated_at"])
    return draft
