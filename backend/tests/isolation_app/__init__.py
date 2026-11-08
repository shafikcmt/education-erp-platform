"""Test-only Django app (installed **only** by ``config.settings.test``).

Its three probe tables are created with the real migration operations (``EnableTenantRLS``,
``EnableDualScopeRLS``). They give the isolation tests real RLS-protected tables to work on,
and give the RLS coverage check (``tests/isolation/test_rls_coverage.py``) the reference
policy shape of each class: every real tenant table's policies must deparse identically.
"""
