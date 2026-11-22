"""Form definitions and the DynamicForm backend (Phase 5 M4; CUSTOMIZATION_ENGINE.md §4.3).

A layout is ``{"sections": [{"key", "labels", "fields": [{"source": "core"|"custom", "name",
"required"?}], "visible_when"?: <rule>}]}``. Visibility rules run in the rules sandbox
(``customization.form_visibility``, variables ``field.<name>`` and ``today``). The same
validation runs for every submission server-side: hidden sections' values are refused, and
required fields are enforced only where visible.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError

from apps.audit.services import record
from apps.core.tenancy import require_tenant
from apps.customization import versioning
from apps.customization.fields import validate_values
from apps.customization.models import FieldDefinition, FormDefinition
from apps.customization.registry import declared_entities, declared_namespaces, entity_core_fields
from apps.customization.rules import RuleError, check, evaluate
from apps.rbac.engine import ScopeTarget, require_perm

if TYPE_CHECKING:
    from django.http import HttpRequest

    from apps.identity.models import User

MANAGE, PUBLISH = "customization.form.manage", "customization.config.publish"
VISIBILITY = "customization.form_visibility"
MAX_SECTIONS, MAX_FIELDS = 20, 60
_KEY = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


def _target() -> ScopeTarget:
    return ScopeTarget(require_tenant().id)


def validate_layout(entity: str, layout: Any) -> dict[str, Any]:
    if entity not in declared_entities():
        raise ValidationError({"entity": "Forms are built for declared entities only."})
    sections = layout.get("sections") if isinstance(layout, dict) else None
    if not isinstance(sections, list) or not 1 <= len(sections) <= MAX_SECTIONS:
        raise ValidationError({"layout": f"Give 1-{MAX_SECTIONS} sections."})
    core = entity_core_fields().get(entity, frozenset())
    custom = {
        f.key for f in FieldDefinition.objects.filter(entity=entity, deprecated_at__isnull=True)
    }
    namespace = declared_namespaces()[VISIBILITY]
    seen_sections: set[str] = set()
    seen_fields: set[str] = set()
    for section in sections:
        if not isinstance(section, dict) or set(section) - {
            "key",
            "labels",
            "fields",
            "visible_when",
        }:
            raise ValidationError({"layout": "A section has key, labels, fields, visible_when."})
        key = section.get("key", "")
        if not isinstance(key, str) or not _KEY.match(key) or key in seen_sections:
            raise ValidationError({"layout": f"Section keys are unique identifiers ({key!r})."})
        seen_sections.add(key)
        for item in section.get("fields", []):
            if not isinstance(item, dict) or item.get("source") not in ("core", "custom"):
                raise ValidationError({"layout": "Each field has a source (core or custom)."})
            name = item.get("name")
            known = core if item["source"] == "core" else custom
            if name not in known:
                raise ValidationError({"layout": f"Unknown {item['source']} field {name!r}."})
            if name in seen_fields:
                raise ValidationError({"layout": f"Field {name!r} appears twice."})
            seen_fields.add(str(name))
        if "visible_when" in section:
            try:
                check(section["visible_when"], namespace)
            except RuleError as exc:
                raise ValidationError({"layout": f"Section {key}: {exc}"}) from None
    if len(seen_fields) > MAX_FIELDS:
        raise ValidationError({"layout": f"A form holds at most {MAX_FIELDS} fields."})
    return layout  # type: ignore[no-any-return]


def save_form_draft(
    *,
    actor: User,
    key: str,
    entity: str,
    name: str,
    layout: Any,
    request: HttpRequest | None = None,
) -> FormDefinition:
    require_perm(actor, MANAGE, target=_target(), use_cache=False)
    current = versioning.published(FormDefinition, key)
    if current is not None and current.entity != entity:
        raise ValidationError({"entity": "A form keeps its entity."})
    validate_layout(entity, layout)
    versioning.check_new_key_quota(FormDefinition, key, "max_forms")
    draft = versioning.draft_for(FormDefinition, key, actor.pk)
    draft.entity, draft.name, draft.layout, draft.updated_by = entity, name, layout, actor.pk
    try:
        draft.full_clean(exclude=["tenant"])
    except ValidationError as exc:
        raise ValidationError(exc.message_dict) from None
    draft.save()
    record(
        "customization.form.draft_saved",
        actor=actor,
        request=request,
        target_type="customization.form",
        target_id=draft.pk,
        metadata={"key": key, "entity": entity, "number": draft.number},
    )
    return draft


def publish_form(*, actor: User, key: str, request: HttpRequest | None = None) -> FormDefinition:
    require_perm(actor, PUBLISH, target=_target(), use_cache=False)
    draft = versioning.draft_or_none(FormDefinition, key)
    if draft is None:
        raise ValidationError({"key": "There is no draft of this form."})
    validate_layout(draft.entity, draft.layout)  # fields may have been deprecated since
    versioning.activate(FormDefinition, draft, actor.pk)
    record(
        "customization.form.published",
        actor=actor,
        request=request,
        target_type="customization.form",
        target_id=draft.pk,
        metadata={"key": key, "entity": draft.entity, "number": draft.number},
    )
    return draft


def _published(key: str) -> FormDefinition:
    form = versioning.published(FormDefinition, key)
    if form is None:
        raise ValidationError({"form": "Unknown or unpublished form."})
    return form


def render(key: str) -> dict[str, Any]:
    """The published form expanded for the DynamicForm renderer (field metadata included)."""
    form = _published(key)
    custom = {f.key: f for f in FieldDefinition.objects.filter(entity=form.entity)}
    sections = []
    for section in form.layout["sections"]:
        fields = []
        for item in section.get("fields", []):
            if item["source"] == "custom":
                field = custom[item["name"]]
                fields.append(
                    {
                        "source": "custom",
                        "name": field.key,
                        "type": field.field_type,
                        "labels": field.labels,
                        "options": field.options,
                        "validation": field.validation,
                        "required": field.required or bool(item.get("required")),
                    }
                )
            else:
                fields.append(
                    {"source": "core", "name": item["name"], "required": bool(item.get("required"))}
                )
        sections.append(
            {
                "key": section["key"],
                "labels": section.get("labels", {}),
                "fields": fields,
                "conditional": "visible_when" in section,
            }
        )
    return {"key": form.key, "entity": form.entity, "version": form.number, "sections": sections}


def _context(form: FormDefinition, values: dict[str, Any], today: dt.date) -> dict[str, Any]:
    names = [i["name"] for s in form.layout["sections"] for i in s.get("fields", [])]
    return {**{f"field.{n}": values.get(n) for n in names}, "today": today}


def visible_sections(
    key: str, values: dict[str, Any], *, today: dt.date | None = None
) -> list[str]:
    form = _published(key)
    namespace = declared_namespaces()[VISIBILITY]
    context = _context(form, values, today or dt.date.today())
    shown = []
    for section in form.layout["sections"]:
        rule = section.get("visible_when")
        try:
            if rule is None or evaluate(rule, namespace, context) is True:
                shown.append(section["key"])
        except RuleError:
            continue  # a rule that can't decide hides its section (fail closed)
    return shown


def validate_submission(
    key: str, values: Any, *, today: dt.date | None = None
) -> dict[str, dict[str, Any]]:
    """Server-side validation of a submission: ``{"core": {...}, "custom": {...}}``."""
    if not isinstance(values, dict):
        raise ValidationError({"values": "A submission is an object of field values."})
    form = _published(key)
    shown = set(visible_sections(key, values, today=today))
    rendered = {s["key"]: s for s in render(key)["sections"]}
    allowed: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    for section_key, section in rendered.items():
        for field in section["fields"]:
            if section_key in shown:
                allowed[field["name"]] = field
            elif values.get(field["name"]) not in (None, "", []):
                errors[field["name"]] = "This field is hidden."
    for name in values:
        if name not in allowed and name not in errors:
            errors[name] = "Unknown field."
    for name, field in allowed.items():
        if field["required"] and values.get(name) in (None, "", []):
            errors[name] = "This field is required."
    custom = {n: v for n, v in values.items() if n in allowed and allowed[n]["source"] == "custom"}
    try:
        validate_values(form.entity, custom, partial=True)
    except ValidationError as exc:
        for name, messages in exc.message_dict.items():
            errors.setdefault(name, messages[0])
    if errors:
        raise ValidationError(errors)
    core = {n: v for n, v in values.items() if n in allowed and allowed[n]["source"] == "core"}
    return {"core": core, "custom": custom}
