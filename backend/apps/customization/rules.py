"""Sandboxed rules evaluator (Phase 5 M3; ADR-055, decides ADR-016).

Rules are JSON ASTs in a JSONLogic-like form: ``{"<op>": [args…]}``, literals, and
``{"var": "<name>"}``. They are **data**: no attribute access, no imports, no loops, no I/O, no
user-defined functions. Before evaluation every rule is checked statically:

* only allow-listed operators (``OPERATORS``);
* only the variables its namespace declares (exact names or ``prefix.*``);
* at most ``MAX_NODES`` nodes, ``MAX_DEPTH`` levels, ``MAX_STRING`` characters per string and
  ``MAX_LIST`` items per list.

Evaluation counts steps (``MAX_STEPS``) and uses ``Decimal`` arithmetic (never floats: JSON
numbers become ``Decimal``); division by zero, type mismatches and unknown values raise
:class:`RuleError`. Results are deterministic: ``today`` comes from the context, not the clock.
"""

from __future__ import annotations

import datetime as dt
import fnmatch
from dataclasses import dataclass
from decimal import Decimal, DivisionByZero, InvalidOperation, localcontext
from typing import Any

MAX_NODES = 500
MAX_DEPTH = 32
MAX_STEPS = 10_000
MAX_STRING = 1_000
MAX_LIST = 200
_ARITY = {
    "==": (2, 2), "!=": (2, 2), "<": (2, 2), "<=": (2, 2), ">": (2, 2), ">=": (2, 2),
    "and": (1, 20), "or": (1, 20), "not": (1, 1),
    "if": (3, 21),
    "+": (1, 20), "-": (1, 2), "*": (1, 20), "/": (2, 2), "min": (1, 20), "max": (1, 20),
    "round": (1, 2), "in": (2, 2), "var": (1, 1), "date": (1, 1), "days_between": (2, 2),
    "missing": (1, 1),
}  # fmt: skip
OPERATORS = frozenset(_ARITY)


class RuleError(ValueError):
    """The rule is invalid or could not be evaluated safely."""


@dataclass(frozen=True)
class Namespace:
    """Where a rule may be used: the variables it may read and the type of its result."""

    code: str
    variables: tuple[str, ...]  # exact names or "prefix.*"
    result: str  # "boolean", "number" or "any"
    description: str = ""

    def allows(self, name: str) -> bool:
        return any(
            name == pattern or (pattern.endswith(".*") and fnmatch.fnmatchcase(name, pattern))
            for pattern in self.variables
        )


# --------------------------------------------------------------------------- static check
def _args(node: dict[str, Any]) -> tuple[str, list[Any]]:
    if len(node) != 1:
        raise RuleError("An operation is an object with exactly one operator.")
    op, raw = next(iter(node.items()))
    if op not in OPERATORS:
        raise RuleError(f"Operator {op!r} is not allowed.")
    args = raw if isinstance(raw, list) else [raw]
    low, high = _ARITY[op]
    if not low <= len(args) <= high:
        raise RuleError(f"{op!r} takes {low}-{high} arguments.")
    if op == "if" and len(args) % 2 == 0:
        raise RuleError("'if' takes condition/value pairs and a final else value.")
    return op, args


def check(rule: Any, namespace: Namespace) -> None:
    """Static validation: shape, operators, variables and size limits."""
    count = 0

    def walk(node: Any, depth: int) -> None:
        nonlocal count
        count += 1
        if count > MAX_NODES:
            raise RuleError(f"The rule has more than {MAX_NODES} nodes.")
        if depth > MAX_DEPTH:
            raise RuleError(f"The rule is nested deeper than {MAX_DEPTH} levels.")
        if node is None or isinstance(node, bool | int | float):
            return
        if isinstance(node, str):
            if len(node) > MAX_STRING:
                raise RuleError("A string in the rule is too long.")
            return
        if isinstance(node, list):
            if len(node) > MAX_LIST:
                raise RuleError("A list in the rule is too long.")
            for item in node:
                walk(item, depth + 1)
            return
        if isinstance(node, dict):
            op, args = _args(node)
            if op in ("var", "missing"):
                if not isinstance(args[0], str) or not namespace.allows(args[0]):
                    raise RuleError(f"Variable {args[0]!r} is not available here.")
                return
            for arg in args:
                walk(arg, depth + 1)
            return
        raise RuleError(f"Unsupported value of type {type(node).__name__}.")

    walk(rule, 0)


# --------------------------------------------------------------------------- evaluation
def _number(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise RuleError("A number was expected.")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            raise RuleError("A number was expected.") from None
    raise RuleError("A number was expected.")


def _date(value: Any) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            raise RuleError("A date (YYYY-MM-DD) was expected.") from None
    raise RuleError("A date was expected.")


def _comparable(a: Any, b: Any) -> tuple[Any, Any]:
    if isinstance(a, str) and isinstance(b, str):
        return a, b
    if isinstance(a, dt.date) or isinstance(b, dt.date):
        return _date(a), _date(b)
    return _number(a), _number(b)


def _equal(a: Any, b: Any) -> bool:
    if a is None or b is None or isinstance(a, bool) or isinstance(b, bool):
        return a is b if (a is None or b is None) else a == b
    if isinstance(a, str) or isinstance(b, str):
        return a == b if isinstance(a, str) and isinstance(b, str) else False
    left, right = _comparable(a, b)
    return bool(left == right)


def evaluate(rule: Any, namespace: Namespace, context: dict[str, Any]) -> Any:
    """Check, then evaluate ``rule`` against ``context`` (flat ``name -> value``)."""
    check(rule, namespace)
    steps = 0

    def ev(node: Any) -> Any:
        nonlocal steps
        steps += 1
        if steps > MAX_STEPS:
            raise RuleError("The rule took too many steps.")
        if isinstance(node, float):
            return Decimal(repr(node))
        if isinstance(node, int) and not isinstance(node, bool):
            return Decimal(node)
        if not isinstance(node, dict):
            return [ev(x) for x in node] if isinstance(node, list) else node
        op, args = _args(node)
        if op == "var":
            if args[0] not in context:
                raise RuleError(f"No value for {args[0]!r}.")
            return context[args[0]]
        if op == "missing":
            return context.get(args[0]) in (None, "", [])
        if op == "and":
            result: Any = True
            for arg in args:
                result = ev(arg)
                if not _truthy(result):
                    return False
            return True
        if op == "or":
            return any(_truthy(ev(arg)) for arg in args)
        if op == "not":
            return not _truthy(ev(args[0]))
        if op == "if":
            for cond, then in zip(args[0:-1:2], args[1:-1:2], strict=True):
                if _truthy(ev(cond)):
                    return ev(then)
            return ev(args[-1])
        values = [ev(arg) for arg in args]
        return _apply(op, values)

    with localcontext() as ctx:
        ctx.prec = 28
        try:
            result = ev(rule)
        except (DivisionByZero, InvalidOperation) as exc:
            raise RuleError("Arithmetic error (e.g. division by zero).") from exc
        except RecursionError:
            raise RuleError("The rule is too deeply nested.") from None
    if namespace.result == "boolean" and not isinstance(result, bool):
        raise RuleError("This rule must produce true or false.")
    if namespace.result == "number" and not isinstance(result, Decimal):
        raise RuleError("This rule must produce a number.")
    return result


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise RuleError("A condition must be true or false.")


def _apply(op: str, v: list[Any]) -> Any:
    if op == "==":
        return _equal(v[0], v[1])
    if op == "!=":
        return not _equal(v[0], v[1])
    if op in ("<", "<=", ">", ">="):
        a, b = _comparable(v[0], v[1])
        return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
    if op == "+":
        return sum((_number(x) for x in v), Decimal(0))
    if op == "-":
        return -_number(v[0]) if len(v) == 1 else _number(v[0]) - _number(v[1])
    if op == "*":
        out = Decimal(1)
        for x in v:
            out *= _number(x)
        return out
    if op == "/":
        divisor = _number(v[1])
        if divisor == 0:
            raise RuleError("Division by zero.")
        return _number(v[0]) / divisor
    if op in ("min", "max"):
        nums = [_number(x) for x in v]
        return min(nums) if op == "min" else max(nums)
    if op == "round":
        places = int(_number(v[1])) if len(v) == 2 else 0
        if not 0 <= places <= 6:
            raise RuleError("'round' keeps 0-6 decimal places.")
        return _number(v[0]).quantize(Decimal(1).scaleb(-places))
    if op == "in":
        haystack = v[1]
        if isinstance(haystack, str):
            return isinstance(v[0], str) and v[0] in haystack
        if isinstance(haystack, list):
            return any(_equal(v[0], item) for item in haystack)
        raise RuleError("'in' needs a list or a string.")
    if op == "date":
        return _date(v[0])
    if op == "days_between":
        return Decimal((_date(v[1]) - _date(v[0])).days)
    raise RuleError(f"Operator {op!r} is not allowed.")  # pragma: no cover - allow-list above
