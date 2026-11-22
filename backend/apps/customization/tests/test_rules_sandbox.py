"""Rules sandbox (Phase 5 M3; ADR-055). Exit criterion: the sandbox security tests pass."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from apps.customization.registry import declared_namespaces
from apps.customization.rules import MAX_DEPTH, MAX_NODES, Namespace, RuleError, check, evaluate

NS = Namespace("test.ns", ("invoice.*", "today", "field.*"), "any")
BOOL = Namespace("test.bool", ("field.*",), "boolean")
NUM = Namespace("test.num", ("invoice.*", "today"), "number")


def test_declared_namespaces_are_loaded():
    spaces = declared_namespaces()
    assert spaces["customization.form_visibility"].result == "boolean"
    assert spaces["customization.form_visibility"].allows("field.age")
    assert not spaces["customization.form_visibility"].allows("subject.x")


@pytest.mark.parametrize(
    ("rule", "context", "expected"),
    [
        ({"+": [1, 2, "0.5"]}, {}, Decimal("3.5")),
        (
            {"*": [{"var": "invoice.balance"}, "0.02"]},
            {"invoice.balance": "1000.00"},
            Decimal("20.0000"),
        ),
        ({"round": [{"/": [10, 3]}, 2]}, {}, Decimal("3.33")),
        (
            {"max": [0, {"-": [{"var": "invoice.balance"}, 500]}]},
            {"invoice.balance": 200},
            Decimal(0),
        ),
        (
            {"days_between": [{"var": "invoice.due_date"}, {"var": "today"}]},
            {"invoice.due_date": "2026-11-01", "today": dt.date(2026, 11, 22)},
            Decimal(21),
        ),
        ({"if": [{">": [{"var": "field.age"}, 17]}, "adult", "minor"]}, {"field.age": 18}, "adult"),
        ({"if": [False, 1, {"==": [1, 1]}, 2, 3]}, {}, Decimal(2)),
        ({"in": ["hifz", ["hifz", "alia"]]}, {}, True),
        ({"and": [{"==": ["a", "a"]}, {"!=": [1, 2]}]}, {}, True),
        ({"missing": "field.note"}, {"field.note": ""}, True),
        ({"<": [{"date": "2026-01-01"}, {"var": "today"}]}, {"today": "2026-11-22"}, True),
    ],
)
def test_evaluation(rule, context, expected):
    assert evaluate(rule, NS, context) == expected


def test_money_never_uses_floats():
    result = evaluate({"+": [0.1, 0.2]}, NUM, {})
    assert isinstance(result, Decimal) and result == Decimal("0.3")


@pytest.mark.parametrize(
    "rule",
    [
        # Code execution / introspection attempts are not operators.
        {"__import__": ["os"]},
        {"eval": ["1+1"]},
        {"exec": ["print(1)"]},
        {"getattr": [{"var": "invoice.balance"}, "__class__"]},
        {"__class__": []},
        {"lambda": [1]},
        {"map": [[1, 2], {"var": "x"}]},
        {"reduce": [[1, 2], {"+": [1, 1]}, 0]},
        # Variables outside the namespace (including dunder paths).
        {"var": "__globals__"},
        {"var": "subject.secret"},
        {"var": "user.password"},
        {"var": ""},
        {"var": ["field.a", "default"]},
        # Malformed operations.
        {"+": [1], "-": [2]},
        {"if": [True, 1]},
        {"not": [1, 2]},
    ],
)
def test_escape_and_malformed_payloads_are_refused(rule):
    with pytest.raises(RuleError):
        check(rule, NS)


def test_dunder_variable_names_never_reach_the_context():
    # Even a namespace wildcard can't read Python internals: values come only from the dict.
    with pytest.raises(RuleError, match="No value"):
        evaluate({"var": "field.__class__"}, NS, {})


def test_resource_limits():
    deep: object = 1
    for _ in range(MAX_DEPTH + 2):
        deep = {"+": [deep]}
    with pytest.raises(RuleError, match="nested"):
        check(deep, NS)
    wide = {"and": [{"==": [1, 1]}] * 20}
    many = {"or": [wide] * 20}  # 1 + 20 * (1 + 20 * 3) nodes, above MAX_NODES
    with pytest.raises(RuleError, match=str(MAX_NODES)):
        check(many, NS)
    with pytest.raises(RuleError, match="too long"):
        check({"==": ["x" * 2000, "y"]}, NS)
    with pytest.raises(RuleError, match="too long"):
        check({"in": [1, list(range(500))]}, NS)


def test_type_and_arithmetic_errors_are_rule_errors_not_crashes():
    cases: list[tuple[dict, dict]] = [
        ({"/": [1, 0]}, {}),
        ({"+": ["abc", 1]}, {}),
        ({"<": [True, 1]}, {}),
        ({"days_between": ["not-a-date", "2026-01-01"]}, {}),
        ({"if": [1, 2, 3]}, {}),  # a condition must be boolean
        ({"var": "invoice.balance"}, {}),  # missing value
        ({"round": [1, 9]}, {}),
    ]
    for rule, context in cases:
        with pytest.raises(RuleError):
            evaluate(rule, NS, context)


def test_result_types_are_enforced():
    with pytest.raises(RuleError, match="true or false"):
        evaluate({"+": [1, 1]}, BOOL, {})
    with pytest.raises(RuleError, match="number"):
        evaluate({"==": [1, 1]}, NUM, {})
    assert evaluate({">": [{"var": "field.n"}, 2]}, BOOL, {"field.n": 3}) is True


def test_evaluation_is_deterministic_and_clock_free():
    rule = {"days_between": [{"var": "invoice.due_date"}, {"var": "today"}]}
    context = {"invoice.due_date": "2026-01-01", "today": "2026-01-31"}
    assert evaluate(rule, NS, context) == evaluate(rule, NS, context) == Decimal(30)
