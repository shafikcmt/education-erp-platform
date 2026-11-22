"""Sandboxed Studio templates (Phase 5 M5; ADR-056).

Templates are rendered by Jinja2's ``ImmutableSandboxedEnvironment`` with extra hardening:

* no loader: ``include``, ``import``, ``extends`` and ``from`` are refused at save time;
* no globals (``range``, ``lipsum``, ``dict``, ``cycler``, ``joiner``, ``namespace`` removed) and
  an allow-listed filter set (no ``attr``, ``format``, ``map``, ``xmlattr`` …);
* the context is plain data only (strings, numbers, booleans, dates, lists and dicts) built per
  template kind from its declared variables; never ORM objects;
* autoescape for HTML kinds; single-line subjects and no control characters for SMS/email;
* source and output size limits; output is generated incrementally and stopped at the limit;
* undefined variables are errors (``StrictUndefined``), so previews show mistakes early.
"""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal
from typing import Any

from jinja2 import StrictUndefined, TemplateError, nodes
from jinja2.exceptions import SecurityError
from jinja2.sandbox import ImmutableSandboxedEnvironment

MAX_SOURCE = 20_000
_FORBIDDEN_NODES = (nodes.Extends, nodes.Include, nodes.Import, nodes.FromImport)
_ALLOWED_FILTERS = (
    "upper", "lower", "title", "capitalize", "trim", "truncate", "default", "length",
    "join", "round", "first", "last", "replace", "escape", "e", "int", "abs", "sort",
    "striptags", "wordcount", "center", "indent",
)  # fmt: skip
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class TemplateRenderError(ValueError):
    """The template is invalid, unsafe, or failed to render within its limits."""


def _date(value: Any, fmt: str = "%Y-%m-%d") -> str:
    if isinstance(value, str):
        value = dt.date.fromisoformat(value)
    if not isinstance(value, dt.date):
        raise TemplateRenderError("'date' needs a date.")
    if not re.fullmatch(r"(%[dmyYbBaA]|[ ./,-])+", fmt):
        raise TemplateRenderError("Unsupported date format.")
    return value.strftime(fmt)


def _environment(html: bool) -> ImmutableSandboxedEnvironment:
    env = ImmutableSandboxedEnvironment(
        autoescape=html,
        undefined=StrictUndefined,
        loader=None,
        auto_reload=False,
        keep_trailing_newline=False,
    )
    env.globals.clear()
    env.filters = {name: env.filters[name] for name in _ALLOWED_FILTERS}
    env.filters["date"] = _date
    env.tests = {
        k: v
        for k, v in env.tests.items()
        if k in ("defined", "none", "number", "string", "even", "odd")
    }
    return env


_ENVS = {False: _environment(False), True: _environment(True)}


def check_source(source: Any, *, html: bool) -> None:
    """Parse-time checks: size, syntax and forbidden constructs."""
    if not isinstance(source, str) or len(source) > MAX_SOURCE:
        raise TemplateRenderError(f"A template is text of at most {MAX_SOURCE} characters.")
    try:
        tree = _ENVS[html].parse(source)
    except TemplateError as exc:
        raise TemplateRenderError(f"Template syntax error: {exc.message}") from None
    if any(True for _ in tree.find_all(_FORBIDDEN_NODES)):
        raise TemplateRenderError("include, import and extends are not allowed.")


def plain(value: Any, depth: int = 0) -> Any:
    """Copy ``value`` keeping only plain data; anything else is refused."""
    if depth > 8:
        raise TemplateRenderError("The template data is nested too deeply.")
    if value is None or isinstance(value, bool | int | str | dt.date):
        return value
    if isinstance(value, Decimal):
        return str(value)  # money stays exact; templates print it as given
    if isinstance(value, float):
        raise TemplateRenderError("Floats are not template data (use strings or Decimal).")
    if isinstance(value, list | tuple):
        if len(value) > 1_000:
            raise TemplateRenderError("A list in the template data is too long.")
        return [plain(v, depth + 1) for v in value]
    if isinstance(value, dict):
        return {str(k): plain(v, depth + 1) for k, v in value.items() if isinstance(k, str)}
    raise TemplateRenderError(f"{type(value).__name__} is not template data.")


def render(source: str, context: dict[str, Any], *, html: bool, max_output: int) -> str:
    check_source(source, html=html)
    try:
        template = _ENVS[html].from_string(source)
        chunks: list[str] = []
        size = 0
        for chunk in template.generate(plain(context)):
            size += len(chunk)
            if size > max_output:
                raise TemplateRenderError(f"The output is longer than {max_output} characters.")
            chunks.append(chunk)
    except SecurityError as exc:
        raise TemplateRenderError(f"Not allowed: {exc}") from None
    except TemplateError as exc:
        raise TemplateRenderError(f"Rendering failed: {exc.message}") from None
    except (TypeError, ValueError, ArithmeticError, RecursionError) as exc:
        if isinstance(exc, TemplateRenderError):
            raise
        raise TemplateRenderError("Rendering failed.") from None
    return "".join(chunks)


def single_line(text: str) -> str:
    if "\n" in text or "\r" in text or _CONTROL.search(text):
        raise TemplateRenderError("This must be a single line of text.")
    return text


def plain_text(text: str) -> str:
    if _CONTROL.search(text):
        raise TemplateRenderError("Control characters are not allowed.")
    return text
