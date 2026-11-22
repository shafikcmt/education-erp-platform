"""Template drafts, previews and publishing (Phase 5 M5; ADR-056).

Every locale's subject and body are checked at save time (syntax, forbidden constructs, size).
Previews render with the kind's sample data (or caller data restricted to the kind's declared
variables). Publishing needs ``customization.config.publish`` and a successful sample render of
every locale. Published versions are immutable.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError

from apps.audit.services import record
from apps.core.tenancy import require_tenant
from apps.customization import versioning
from apps.customization.models import TemplateDefinition
from apps.customization.registry import declared_template_kinds
from apps.customization.templates_engine import (
    TemplateRenderError,
    check_source,
    plain_text,
    render,
    single_line,
)
from apps.rbac.engine import ScopeTarget, require_perm

if TYPE_CHECKING:
    from django.http import HttpRequest

    from apps.identity.models import User

MANAGE, PUBLISH = "customization.template.manage", "customization.config.publish"
LOCALE = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")


def _target() -> ScopeTarget:
    return ScopeTarget(require_tenant().id)


def _kind(code: str) -> dict[str, Any]:
    kind = declared_template_kinds().get(code)
    if kind is None:
        raise ValidationError({"kind": "Unknown template kind."})
    return kind


def _check_content(kind: dict[str, Any], content: Any) -> dict[str, Any]:
    if not isinstance(content, dict) or not content or len(content) > 10:
        raise ValidationError({"content": "Give the template for 1-10 locales."})
    html = kind["format"] == "html"
    for locale, parts in content.items():
        if not LOCALE.match(locale) or not isinstance(parts, dict):
            raise ValidationError({"content": f"Invalid locale entry {locale!r}."})
        expected = {"subject", "body"} if kind.get("subject") else {"body"}
        if set(parts) != expected:
            raise ValidationError({"content": f"{locale}: give {sorted(expected)}."})
        try:
            for part in expected:
                check_source(parts[part], html=html and part == "body")
        except TemplateRenderError as exc:
            raise ValidationError({"content": f"{locale}: {exc}"}) from None
    return content


def _render_parts(
    kind: dict[str, Any], content: dict[str, Any], locale: str, data: dict[str, Any]
) -> dict[str, str]:
    parts = content.get(locale)
    if parts is None:
        raise ValidationError({"locale": "This template has no text for that language."})
    unknown = set(data) - set(kind["variables"])
    if unknown:
        raise ValidationError({"context": f"Undeclared variables: {sorted(unknown)}."})
    html = kind["format"] == "html"
    out: dict[str, str] = {}
    try:
        body = render(parts["body"], data, html=html, max_output=int(kind["max_output"]))
        out["body"] = body if html else plain_text(body)
        if kind.get("subject"):
            out["subject"] = single_line(render(parts["subject"], data, html=False, max_output=200))
    except TemplateRenderError as exc:
        raise ValidationError({"content": f"{locale}: {exc}"}) from None
    return out


def save_template_draft(
    *,
    actor: User,
    key: str,
    kind_code: str,
    name: str,
    content: Any,
    request: HttpRequest | None = None,
) -> TemplateDefinition:
    require_perm(actor, MANAGE, target=_target(), use_cache=False)
    kind = _kind(kind_code)
    current = versioning.published(TemplateDefinition, key)
    if current is not None and current.kind != kind_code:
        raise ValidationError({"kind": "A template keeps its kind."})
    _check_content(kind, content)
    versioning.check_new_key_quota(TemplateDefinition, key, "max_templates")
    draft = versioning.draft_for(TemplateDefinition, key, actor.pk)
    draft.kind, draft.name, draft.content, draft.updated_by = kind_code, name, content, actor.pk
    try:
        draft.full_clean(exclude=["tenant"])
    except ValidationError as exc:
        raise ValidationError(exc.message_dict) from None
    draft.save()
    record(
        "customization.template.draft_saved",
        actor=actor,
        request=request,
        target_type="customization.template",
        target_id=draft.pk,
        metadata={"key": key, "kind": kind_code, "number": draft.number},
    )
    return draft


def preview(
    *, kind_code: str, content: Any, locale: str, data: dict[str, Any] | None = None
) -> dict[str, str]:
    kind = _kind(kind_code)
    _check_content(kind, content)
    return _render_parts(
        kind, content, locale, dict(kind.get("sample", {})) if data is None else data
    )


def publish_template(
    *, actor: User, key: str, request: HttpRequest | None = None
) -> TemplateDefinition:
    require_perm(actor, PUBLISH, target=_target(), use_cache=False)
    draft = versioning.draft_or_none(TemplateDefinition, key)
    if draft is None:
        raise ValidationError({"key": "There is no draft of this template."})
    kind = _kind(draft.kind)
    _check_content(kind, draft.content)
    for locale in draft.content:  # every language must render with the sample data
        _render_parts(kind, draft.content, locale, dict(kind.get("sample", {})))
    versioning.activate(TemplateDefinition, draft, actor.pk)
    record(
        "customization.template.published",
        actor=actor,
        request=request,
        target_type="customization.template",
        target_id=draft.pk,
        metadata={"key": key, "kind": draft.kind, "number": draft.number},
    )
    return draft


def render_published(key: str, locale: str, data: dict[str, Any]) -> dict[str, str]:
    """Render the published version (used by notifications and documents)."""
    template = versioning.published(TemplateDefinition, key)
    if template is None:
        raise ValidationError({"template": "Unknown or unpublished template."})
    return _render_parts(_kind(template.kind), template.content, locale, data)
