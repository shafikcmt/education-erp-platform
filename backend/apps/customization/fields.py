"""Custom field definitions and value validation (Phase 5 M3; CUSTOMIZATION_ENGINE.md §4.2).

Only entities declared in a module manifest (``CUSTOM_FIELD_ENTITIES``) accept custom fields.
Values live in the entity's ``extra`` JSONB under the field key and are validated on every
write by :func:`validate_values` against the active definitions: unknown and deprecated keys
are refused, required fields are enforced, and each type has a fixed JSON Schema (decimals
are strings, never floats). ``key`` and ``field_type`` never change.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.services import record
from apps.core.tenancy import require_tenant
from apps.customization.models import FieldDefinition
from apps.customization.registry import declared_entities
from apps.rbac.engine import ScopeTarget, require_perm
from apps.rbac.registry import declared_permissions

if TYPE_CHECKING:
    from django.http import HttpRequest

    from apps.identity.models import User

MANAGE = "customization.field.manage"
LOCALE = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")
_VALIDATION_KEYS = {
    "text": {"min_length", "max_length"},
    "long_text": {"min_length", "max_length"},
    "number": {"min", "max"},
    "decimal": {"min", "max", "places"},
    "date": set(),
    "boolean": set(),
    "single_select": set(),
    "multi_select": {"max_items"},
    "email": set(),
    "phone": set(),
}
_CHANGEABLE = {
    "labels", "required", "options", "validation", "visibility",
    "view_permission", "edit_permission", "pii", "order",
}  # fmt: skip


def _target() -> ScopeTarget:
    return ScopeTarget(require_tenant().id)


def _labels(value: Any) -> dict[str, str]:
    if (
        not isinstance(value, dict)
        or not value
        or not all(
            LOCALE.match(k) and isinstance(v, str) and 0 < len(v) <= 80 for k, v in value.items()
        )
    ):
        raise ValidationError({"labels": "Give a label (1-80 characters) per locale."})
    return dict(value)


def _clean_definition(field_type: str, values: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(values)
    if "labels" in cleaned:
        cleaned["labels"] = _labels(cleaned["labels"])
    if "options" in cleaned:
        options = cleaned["options"] or []
        if field_type in ("single_select", "multi_select"):
            if not isinstance(options, list) or not 1 <= len(options) <= 100:
                raise ValidationError({"options": "Give 1-100 options."})
            seen = set()
            for option in options:
                if not isinstance(option, dict) or not re.match(
                    r"^[a-z0-9_]{1,40}$", str(option.get("value", ""))
                ):
                    raise ValidationError({"options": "Each option has a value (a-z, 0-9, _)."})
                if option["value"] in seen:
                    raise ValidationError({"options": "Option values are unique."})
                seen.add(option["value"])
                _labels(option.get("labels"))
        elif options:
            raise ValidationError({"options": "Only choice fields have options."})
    if "validation" in cleaned:
        rules = cleaned["validation"] or {}
        allowed = _VALIDATION_KEYS[field_type]
        if not isinstance(rules, dict) or set(rules) - allowed:
            raise ValidationError({"validation": f"Allowed: {sorted(allowed) or 'none'}."})
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in rules.values()):
            raise ValidationError({"validation": "Limits are whole numbers."})
    known = declared_permissions()
    for name in ("view_permission", "edit_permission"):
        code = cleaned.get(name) or ""
        if code and code not in known:
            raise ValidationError({name: "Unknown permission code."})
    return cleaned


def define_field(
    *,
    actor: User,
    entity: str,
    key: str,
    field_type: str,
    labels: dict[str, str],
    request: HttpRequest | None = None,
    **options: Any,
) -> FieldDefinition:
    require_perm(actor, MANAGE, target=_target(), use_cache=False)
    if entity not in declared_entities():
        raise ValidationError({"entity": "This entity doesn't accept custom fields."})
    if field_type not in FieldDefinition.FieldType.values:
        raise ValidationError({"field_type": "Unknown field type."})
    unknown = set(options) - (_CHANGEABLE - {"labels"})
    if unknown:
        raise ValidationError(dict.fromkeys(unknown, "Unknown attribute."))
    # Options are always checked on creation: a choice field needs them, other types none.
    from apps.customization import quotas

    quotas.check(
        "max_custom_fields_per_entity",
        FieldDefinition.objects.filter(entity=entity, deprecated_at__isnull=True).count(),
    )
    values = _clean_definition(
        field_type, {"labels": labels, "options": options.pop("options", []), **options}
    )
    field = FieldDefinition(
        entity=entity, key=key, field_type=field_type, created_by=actor.pk, **values
    )
    try:
        field.full_clean(exclude=["tenant"])
        with transaction.atomic():
            field.save()
    except IntegrityError:
        raise ValidationError({"key": "A field with this key exists for this entity."}) from None
    except ValidationError as exc:
        raise ValidationError(exc.message_dict) from None
    record(
        "customization.field.defined",
        actor=actor,
        request=request,
        target_type="customization.field",
        target_id=field.pk,
        metadata={"entity": entity, "key": key, "field_type": field_type},
    )
    return field


def update_field(
    *,
    actor: User,
    field: FieldDefinition,
    changes: dict[str, Any],
    request: HttpRequest | None = None,
) -> FieldDefinition:
    require_perm(actor, MANAGE, target=_target(), use_cache=False)
    refused = set(changes) - _CHANGEABLE
    if refused:
        raise ValidationError(
            dict.fromkeys(refused, "Key and type never change: deprecate and create a new field.")
        )
    values = _clean_definition(field.field_type, changes)
    for name, value in values.items():
        setattr(field, name, value)
    field.updated_by = actor.pk
    field.save()
    record(
        "customization.field.updated",
        actor=actor,
        request=request,
        target_type="customization.field",
        target_id=field.pk,
        metadata={"entity": field.entity, "key": field.key, "changed": sorted(values)},
    )
    return field


def deprecate_field(
    *, actor: User, field: FieldDefinition, request: HttpRequest | None = None
) -> FieldDefinition:
    require_perm(actor, MANAGE, target=_target(), use_cache=False)
    if field.deprecated_at is None:
        field.deprecated_at = timezone.now()
        field.save(update_fields=["deprecated_at", "updated_at"])
        record(
            "customization.field.deprecated",
            actor=actor,
            request=request,
            target_type="customization.field",
            target_id=field.pk,
            metadata={"entity": field.entity, "key": field.key},
        )
    return field


def _schema(field: FieldDefinition) -> dict[str, Any]:
    rules = field.validation or {}
    kind = field.field_type
    if kind in ("text", "long_text"):
        return {
            "type": "string",
            "minLength": rules.get("min_length", 0),
            "maxLength": rules.get("max_length", 200 if kind == "text" else 5000),
        }
    if kind == "number":
        schema: dict[str, Any] = {"type": "integer"}
        if "min" in rules:
            schema["minimum"] = rules["min"]
        if "max" in rules:
            schema["maximum"] = rules["max"]
        return schema
    if kind == "decimal":  # strings only: never floats (CLAUDE.md §11)
        places = rules.get("places", 2)
        return {"type": "string", "pattern": rf"^-?\d{{1,16}}(\.\d{{1,{places}}})?$"}
    if kind == "date":
        return {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"}
    if kind == "boolean":
        return {"type": "boolean"}
    values = [o["value"] for o in field.options or []]
    if kind == "single_select":
        return {"enum": values}
    if kind == "multi_select":
        return {
            "type": "array",
            "items": {"enum": values},
            "uniqueItems": True,
            "maxItems": rules.get("max_items", len(values)),
        }
    if kind == "email":
        return {"type": "string", "maxLength": 254, "pattern": r"^[^@\s]+@[^@\s]+\.[^@\s]+$"}
    return {"type": "string", "pattern": r"^\+?[0-9 ()-]{4,20}$"}  # phone


def validate_values(entity: str, values: Any, *, partial: bool = False) -> dict[str, Any]:
    """Validate ``values`` for ``entity`` against the tenant's active definitions."""
    import datetime as dt
    from decimal import Decimal

    from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

    if not isinstance(values, dict):
        raise ValidationError({"extra": "Custom field values are an object."})
    fields = {f.key: f for f in FieldDefinition.objects.filter(entity=entity)}
    errors: dict[str, str] = {}
    for key, value in values.items():
        field = fields.get(key)
        if field is None:
            errors[key] = "Unknown field."
            continue
        if field.deprecated_at is not None:
            errors[key] = "This field is deprecated."
            continue
        if value is None:
            if field.required:
                errors[key] = "This field is required."
            continue
        problem = next(iter(Draft202012Validator(_schema(field)).iter_errors(value)), None)
        if problem is not None:
            errors[key] = "Invalid value."
            continue
        if field.field_type == "date":
            try:
                dt.date.fromisoformat(value)
            except ValueError:
                errors[key] = "Invalid date."
        if field.field_type == "decimal":
            number = Decimal(value)
            rules = field.validation or {}
            if ("min" in rules and number < rules["min"]) or (
                "max" in rules and number > rules["max"]
            ):
                errors[key] = "Out of range."
    if not partial:
        for key, field in fields.items():
            if field.required and field.deprecated_at is None and values.get(key) in (None, ""):
                errors.setdefault(key, "This field is required.")
    if errors:
        raise ValidationError(errors)
    return dict(values)


def _holds(actor: Any, code: str, target: Any) -> bool:
    from apps.rbac.engine import has_perm

    return not code or has_perm(actor, code, target=target)


def merge_for_update(
    entity: str, current: Any, incoming: Any, actor: Any, target: Any
) -> dict[str, Any]:
    """``TENANCY_CUSTOM_FIELDS`` hook: merge ``incoming`` into an entity's ``extra``.

    Keys are validated against the active definitions; ``None`` clears a value (refused for
    required fields); a field with an ``edit_permission`` needs it in the object's scope."""
    if not isinstance(incoming, dict):
        raise ValidationError({"extra": "Custom field values are an object."})
    fields = {f.key: f for f in FieldDefinition.objects.filter(entity=entity)}
    denied = [
        key
        for key in incoming
        if key in fields and not _holds(actor, fields[key].edit_permission, target)
    ]
    if denied:
        raise ValidationError(dict.fromkeys(denied, "You can't change this field."))
    validate_values(entity, {k: v for k, v in incoming.items() if v is not None}, partial=True)
    cleared = [k for k, v in incoming.items() if v is None]
    for key in cleared:
        if key not in fields:
            raise ValidationError({key: "Unknown field."})
        if fields[key].required and fields[key].deprecated_at is None:
            raise ValidationError({key: "This field is required."})
    merged = dict(current or {})
    merged.update({k: v for k, v in incoming.items() if v is not None})
    for key in cleared:
        merged.pop(key, None)
    return merged


def visible_values(entity: str, values: Any, actor: Any, target: Any) -> dict[str, Any]:
    """Field-level masking: drop values whose ``view_permission`` the viewer lacks."""
    if not values:
        return {}
    restricted = {
        f.key: f.view_permission
        for f in FieldDefinition.objects.filter(entity=entity).exclude(view_permission="")
    }
    return {
        key: value
        for key, value in values.items()
        if key not in restricted or _holds(actor, restricted[key], target)
    }
