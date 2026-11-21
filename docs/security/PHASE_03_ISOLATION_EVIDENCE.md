# Phase 3 — Isolation Evidence (threat-model mapping and §23 checklist)

- **Status:** Phase 3 M10, **partial**. This file maps the threat model (plan §14) and the final approval checklist (plan §23) to the tests that exist **today** on `main` plus branch `feat/phase-03-m10`. Rows without evidence say so; nothing is claimed that has not been run.
- **Date:** 2026-11-19.
- **How it was verified:** local runs. Backend: 874 passed, 9 skipped. Playwright: 34 passed and 1 skipped, against a Docker stack with tenant hosts on `*.localhost`. GitHub CI results are recorded in the PR.
- Paths are relative to `backend/` unless they start with `frontend/`.

## 1. Threat model (plan §14) → tests

| # | Threat | Evidence (tests) | State |
|---|---|---|---|
| T1 | Cross-tenant read/write (IDOR) | `tests/isolation/test_rls_coverage.py`, `apps/tenancy/tests/test_table_isolation.py`, `apps/tenancy/tests/test_api_tenant.py::test_another_tenants_objects_are_plain_404s`, `frontend/e2e/tenants.spec.ts` (other tenant out of reach) | Covered |
| T2 | Missing filter in new code | `apps/core/tests/test_tenant_scoped_model.py` (fail-closed manager), `tests/isolation/test_rls_coverage.py` (every table has RLS), `tests/isolation/test_static_checks.py` | Covered |
| T3 | Context leakage across pooled connections | `apps/core/tests/test_tenant_atomic.py` (L-series), `tests/isolation/test_concurrency.py` (K1, K2), `tests/isolation/test_request_concurrency.py` (K8), K3 through the stack in `frontend/e2e/tenants.spec.ts` | Covered |
| T4 | Context leakage in Celery | `tests/isolation/test_tasks.py` (C1–C10, K6 threaded worker) | Covered; prefork K6 through the compose worker **not run** |
| T5 | Host-header spoofing / unknown hosts | `apps/tenancy/tests/test_hosts.py`, `apps/tenancy/tests/test_request_lifecycle.py` (forwarded-host headers ignored, `session_host_mismatch`) | Covered |
| T6 | Tenant enumeration | `apps/tenancy/tests/test_request_lifecycle.py` (uniform 404), `apps/tenancy/tests/test_tenant_sign_in.py` (identical refusals, D7), E2E generic refusal on the other host | Covered |
| T7 | Slug reuse | `apps/tenancy/tests/test_registry.py` (immutable, reserved, tombstoned), `apps/tenancy/tests/test_api_platform.py` (failed provisioning keeps the slug) | Covered |
| T8 | Privilege escalation inside a tenant | `apps/tenancy/tests/test_tenant_rbac.py`, `apps/tenancy/tests/test_api_tenant.py::test_assignments_are_granted_in_scope_without_escalation` | Covered |
| T9 | Super Admin over-reach | `apps/tenancy/tests/test_tenant_sign_in.py` (platform staff without a session refused), `apps/tenancy/tests/test_tenant_rbac.py` | Covered |
| T10 | Support-session abuse | `apps/tenancy/tests/test_support_sessions.py` (S1–S10, K7), `apps/tenancy/tests/test_api_platform.py` (P6 over HTTP), E2E approval and revoke | Covered |
| T11 | Stale permissions after revocation | `apps/tenancy/tests/test_revocation.py` (K5), `apps/tenancy/tests/test_api_tenant.py::test_member_lists_and_lifecycle` | Covered |
| T12 | Invitation hijack | `apps/tenancy/tests/test_invitations.py`, `apps/tenancy/tests/test_api_tenant.py` (acceptance with or without an account; throttled password attempts) | Covered |
| T13 | Cross-tenant FK reference | `apps/tenancy/tests/test_composite_keys.py` | Covered |
| T14 | Cross-subdomain CSRF / cookie tossing | `apps/core/tests/test_settings.py` (`__Host-` cookie in production settings); host-only sessions (T5) | Covered |
| T15 | Platform tasks touching tenant data | `tests/isolation/test_tasks.py` (declaration test, C8) | Covered |
| T16 | `SECURITY DEFINER` misuse | `apps/tenancy/tests/test_definer_functions.py`, `tests/isolation/test_rls_coverage.py`, `tests/isolation/test_static_checks.py` | Covered |
| T17 | Durable-audit bypass | `apps/audit/tests/test_durable.py` (R1–R4) | Covered |
| T18 | Existence oracle through constraint errors | `apps/tenancy/tests/test_composite_keys.py` | Covered |
| T19 | Hidden `BYPASSRLS` path | `apps/core/tests/test_db_roles.py`, `tests/isolation/test_db_role_restrictions.py`, `tests/isolation/test_static_checks.py` | Covered |
| T20 | Platform operation creep | `tests/test_platform_catalogue_completeness.py`, `tests/isolation/test_platform_scope.py` | Covered |
| T21 | Long transactions as a DoS vector | `apps/core/tests/test_tenant_atomic.py`, `apps/tenancy/tests/test_request_lifecycle.py` (`lock_timeout`), `tests/test_keys_and_io_guard.py` (no I/O inside tenant transactions) | **Partial**: the isolation-overhead benchmark (D9) has not been run |
| T22 | Registry table leaks across tenants | `apps/tenancy/tests/test_table_isolation.py`, `apps/tenancy/tests/test_registry.py` | Covered |
| T23 | Premature tenant exposure in production | `apps/core/tests/test_config_guards.py`, `apps/tenancy/tests/test_api_platform.py` (`409 tenant_hosts_disabled`) | Covered |
| T24 | Context in spawned threads or streaming bodies | `apps/core/tests/test_tenant_atomic.py`, `apps/tenancy/tests/test_request_lifecycle.py` (streaming refused) | Covered |

## 2. Security monitoring (plan §14)

| Item | State |
|---|---|
| `tenancy.isolation.blocked` platform events for guard violations, conflicts and session host mismatches (P14) | Implemented and tested (`apps/tenancy/tests/test_request_lifecycle.py`) |
| Structured logs with `tenant_id` and `tx_ms`; warning above 2 s (D9) | Implemented (`TenantTransactionMiddleware`) |
| Sentry alerts on `TenantContextNotApplied` / `TenantContextConflict` | **Not configured**: no Sentry project or DSN exists yet. Accounts are not created without the owner (sprint rules) |
| Daily platform report of denials per tenant | Implemented: `tenancy.report_isolation_denials` (P14), tested in `apps/tenancy/tests/test_isolation_report.py` |

## 3. Final approval checklist (plan §23) → evidence

| Requirement | Evidence | State |
|---|---|---|
| ADR-009 stays Accepted; the amendment is documented | `docs/DECISION_LOG.md` (ADR-043 and its note under ADR-009) | Documented |
| Every `SECURITY DEFINER` function has a threat model and tests | Plan §7; T16 row | Covered |
| Platform operations can't silently bypass RLS | T19 and T20 rows; P10 count tests in `tests/isolation/test_dual_scope_tables.py` | Covered |
| Isolated, transaction-scoped context for every request and task | T3 and T4 rows; `CONN_MAX_AGE = 0` guard in `apps/core/tests/test_config_guards.py` | Covered, except prefork K6 |
| Support sessions can't bypass tenant isolation | T10 row; R9 in `apps/tenancy/tests/test_support_sessions.py` | Covered |
| Tenant hosts disabled until the production domain and security review are approved | T23 row; compose default `TENANT_HOSTS_ENABLED=false`. Only the throwaway CI/E2E stack enables `*.localhost`, which production refuses | Covered |

## 4. Not done in M10 (recorded, not hidden)

1. **Isolation-overhead benchmark (D9, plan §8.4).** Not run. The methodology needs a benchmark-only settings module, a scratch database with a no-RLS control copy, and a seeded workload. Numbers are never estimated.
2. **Tenant-host E2E** runs the full two-tenant journey on desktop in English, and a Bengali owner journey (invitation, MFA enrolment, home, unknown-host 404) on mobile. The full journey is not repeated in Bengali on mobile.
3. **K3** is implemented as concurrent Playwright requests through Nginx and the ASGI server. It sends rounds of 10, within Nginx's per-IP rate limit. The plan's standard-library-threads variant is not implemented; the property tested is the same.
4. **Prefork K6** through the compose worker: not run.
5. **Monitoring:** Sentry alerts (§2 above). The daily denial report exists since M10 part 2.

### Change notes
- 2026-11-19 — Created (Phase 3 M10, partial).
- 2026-11-21 — M10 part 2: daily denial report, Bengali/mobile tenant-host E2E.
- 2026-11-21 — ADR-049: D9 benchmark moved to Phase 18.
