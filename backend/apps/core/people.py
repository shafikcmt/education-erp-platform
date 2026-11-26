"""Validation of a person's core values, shared by students, guardians and staff (Phase 7).

Plain Django only (``core`` imports no other app). Errors are keyed by field so the API answers
them field by field.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

_PHONE = re.compile(r"^\+?[0-9][0-9 ()-]{5,30}$")


def normalise_phone(value: Any) -> str:
    """Digits with an optional leading ``+`` (spaces, dashes and brackets dropped)."""
    text = str(value or "").strip()
    if not text:
        return ""
    if not _PHONE.match(text):
        raise ValidationError({"phone": "Enter a valid phone number."})
    return ("+" if text.startswith("+") else "") + re.sub(r"\D", "", text)


def validate_person(values: dict[str, Any], allowed: frozenset[str]) -> dict[str, Any]:
    """Validate the core values of a person (a student, a guardian or a staff member); only the
    keys in ``allowed`` are accepted."""
    unknown = set(values) - allowed
    if unknown:
        raise ValidationError(dict.fromkeys(sorted(unknown), "Unknown field."))
    out: dict[str, Any] = {}
    errors: dict[str, str] = {}
    if "name" in values:
        name = str(values["name"] or "").strip()
        if not name or len(name) > 160:
            errors["name"] = "Give a name of at most 160 characters."
        out["name"] = name
    if "name_i18n" in values:
        labels = values["name_i18n"] or {}
        if not isinstance(labels, dict) or not all(
            isinstance(k, str) and isinstance(v, str) and len(v) <= 160 for k, v in labels.items()
        ):
            errors["name_i18n"] = "Names per language are text."
        out["name_i18n"] = labels
    if "email" in values:
        email = str(values["email"] or "").strip().lower()
        if email:
            try:
                validate_email(email)
            except ValidationError:
                errors["email"] = "Enter a valid email address."
        out["email"] = email
    if "phone" in values:
        try:
            out["phone"] = normalise_phone(values["phone"])
        except ValidationError:
            errors["phone"] = "Enter a valid phone number."
    if "date_of_birth" in values:
        raw = values["date_of_birth"]
        try:
            out["date_of_birth"] = (
                None if raw in (None, "") else
                raw if isinstance(raw, dt.date) else dt.date.fromisoformat(str(raw))
            )  # fmt: skip
        except ValueError:
            errors["date_of_birth"] = "Use the date format YYYY-MM-DD."
        else:
            dob = out["date_of_birth"]
            if dob is not None and dob > dt.date.today():
                errors["date_of_birth"] = "The date of birth is in the future."
    if "joining_date" in values:
        raw = values["joining_date"]
        try:
            out["joining_date"] = (
                None if raw in (None, "") else
                raw if isinstance(raw, dt.date) else dt.date.fromisoformat(str(raw))
            )  # fmt: skip
        except ValueError:
            errors["joining_date"] = "Use the date format YYYY-MM-DD."
    if "gender" in values:
        gender = str(values["gender"] or "").strip()
        if len(gender) > 32:
            errors["gender"] = "At most 32 characters."
        out["gender"] = gender
    if errors:
        raise ValidationError(errors)
    return out
