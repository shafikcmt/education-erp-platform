"""Numbering sequences (Phase 5 M5; CUSTOMIZATION_ENGINE.md §4.7).

Patterns use ``{INST}``, ``{CAMPUS}``, ``{YYYY}``, ``{YY}``, ``{AY}`` and exactly one
``{SEQ:n}`` (zero-padded to ``n`` digits); other characters are letters, digits and ``/-_.``.
:func:`allocate` runs inside the caller's business transaction and locks the counter row, so
numbers are gap-free: if the transaction rolls back, so does the counter.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.audit.services import record
from apps.core.tenancy import require_tenant
from apps.customization.models import NumberCounter, NumberingSequence
from apps.rbac.engine import ScopeTarget, require_perm

if TYPE_CHECKING:
    from django.http import HttpRequest

    from apps.identity.models import User

MANAGE = "customization.numbering.manage"
_TOKEN = re.compile(r"\{(INST|CAMPUS|YYYY|YY|AY|SEQ:(\d{1,2}))\}")
_LITERAL = re.compile(r"^[A-Za-z0-9/._-]*$")


def validate_pattern(pattern: str, scope: str) -> None:
    if not isinstance(pattern, str) or not 3 <= len(pattern) <= 64:
        raise ValidationError({"pattern": "A pattern has 3-64 characters."})
    seqs = [m for m in _TOKEN.finditer(pattern) if m.group(1).startswith("SEQ")]
    if len(seqs) != 1 or not 1 <= int(seqs[0].group(2)) <= 12:
        raise ValidationError({"pattern": "Use exactly one {SEQ:n} with n from 1 to 12."})
    if not _LITERAL.match(_TOKEN.sub("", pattern)):
        raise ValidationError({"pattern": "Only letters, digits, /, ., _ and - besides tokens."})
    if "{INST}" in pattern and scope == "tenant":
        raise ValidationError({"pattern": "{INST} needs an institution or campus scope."})
    if "{CAMPUS}" in pattern and scope != "campus":
        raise ValidationError({"pattern": "{CAMPUS} needs a campus scope."})


def define_sequence(
    *,
    actor: User,
    key: str,
    name: str,
    pattern: str,
    scope: str = "tenant",
    reset: str = "never",
    request: HttpRequest | None = None,
) -> NumberingSequence:
    require_perm(actor, MANAGE, target=ScopeTarget(require_tenant().id), use_cache=False)
    if scope not in NumberingSequence.Scope.values or reset not in NumberingSequence.Reset.values:
        raise ValidationError({"scope": "Unknown scope or reset."})
    validate_pattern(pattern, scope)
    sequence = NumberingSequence(
        key=key, name=name, pattern=pattern, scope=scope, reset=reset, created_by=actor.pk
    )
    try:
        sequence.full_clean(exclude=["tenant"])
        with transaction.atomic():
            sequence.save()
    except IntegrityError:
        raise ValidationError({"key": "A sequence with this key exists."}) from None
    except ValidationError as exc:
        raise ValidationError(exc.message_dict) from None
    record(
        "customization.numbering.defined",
        actor=actor,
        request=request,
        target_type="customization.numbering",
        target_id=sequence.pk,
        metadata={"key": key, "pattern": pattern, "scope": scope, "reset": reset},
    )
    return sequence


def _academic_year(today: dt.date, institution_id: uuid.UUID | None) -> str:
    from apps.customization.resolver import get_effective_config
    from apps.customization.scopes import ConfigScope

    start = int(
        get_effective_config(ConfigScope(institution_id), "tenancy.academic_year_start_month")
    )
    first = today.year if today.month >= start else today.year - 1
    return f"{first}-{str(first + 1)[-2:]}" if start != 1 else str(first)


def allocate(
    key: str,
    *,
    institution: Any = None,
    campus: Any = None,
    today: dt.date | None = None,
) -> str:
    """Next number of sequence ``key`` (call inside the business transaction)."""
    require_tenant()  # fail closed outside a tenant transaction
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("allocate() runs inside the business transaction.")
    sequence = NumberingSequence.objects.filter(key=key, archived_at__isnull=True).first()
    if sequence is None:
        raise ValidationError({"sequence": "Unknown numbering sequence."})
    if sequence.scope != "tenant" and institution is None:
        raise ValidationError({"institution": "This sequence is numbered per institution."})
    if sequence.scope == "campus" and campus is None:
        raise ValidationError({"campus": "This sequence is numbered per campus."})
    today = today or dt.date.today()
    inst_id = institution.pk if institution is not None and sequence.scope != "tenant" else None
    campus_id = campus.pk if campus is not None and sequence.scope == "campus" else None
    period = {
        "never": "",
        "yearly": str(today.year),
        "academic_year": _academic_year(today, inst_id),
    }[sequence.reset]
    keys = {
        "sequence": sequence,
        "institution_id": inst_id,
        "campus_id": campus_id,
        "period": period,
    }
    counter = NumberCounter.objects.select_for_update().filter(**keys).first()
    if counter is None:
        try:
            with transaction.atomic():
                NumberCounter.objects.create(**keys, value=0)
        except IntegrityError:
            pass  # created concurrently; lock it below
        counter = NumberCounter.objects.select_for_update().get(**keys)
    counter.value += 1
    counter.save(update_fields=["value", "updated_at"])
    values = {
        "INST": getattr(institution, "code", "") or "",
        "CAMPUS": getattr(campus, "code", "") or "",
        "YYYY": str(today.year),
        "YY": str(today.year)[-2:],
        "AY": _academic_year(today, inst_id) if "{AY}" in sequence.pattern else "",
    }

    def replace(match: re.Match[str]) -> str:
        if match.group(1).startswith("SEQ"):
            return str(counter.value).zfill(int(match.group(2)))
        return values[match.group(1)]

    return _TOKEN.sub(replace, sequence.pattern)
