"""Stable Problem Details error of the entitlement engine (ADR-052)."""

from rest_framework import status

from apps.core.exceptions import ProblemError


class ModuleNotEntitledError(ProblemError):
    status_code = status.HTTP_403_FORBIDDEN
    problem_code = "module_not_entitled"
    title = "Module not included"
    default_detail = "Your organisation's plan doesn't include this module."
