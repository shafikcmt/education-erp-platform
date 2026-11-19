# Testing Strategy

> "Done" requires: tests written, tests passing, lint passing, type checks passing — with real output reported (`CLAUDE.md` §0, §17).

## 1. Test pyramid

| Level | Tools | Scope | Runs |
|---|---|---|---|
| Unit | pytest; Vitest | Pure functions, services, rule evaluator, grading calculators, money utilities, components, hooks | Every PR |
| Integration / API | pytest-django + DRF APIClient, real PostgreSQL (with RLS) and Redis | Endpoints, permissions, tenant isolation, transactions, migrations | Every PR |
| Contract | OpenAPI schema generation + TS client drift check | Backend ↔ frontend contract | Every PR |
| E2E | Playwright against Compose stack | Critical user journeys per role | Every PR (smoke set) / nightly (full) |
| Performance | Locust or k6 (decide in Phase 18) | Load on key endpoints with seeded volumes | Before releases (Phase 18+) |
| Security | Isolation suite, authz matrix, dependency scans, ZAP baseline (Phase 18) | | PR + scheduled |

**No SQLite for tests** — tests run on PostgreSQL 17 to exercise JSONB, RLS, constraints and pgvector.

## 2. Mandatory tests per module (definition of done)

1. **Service unit tests** for business rules, including edge cases and failure paths.
2. **Permission tests**: for each endpoint, at least one *allowed* and one *denied* case (wrong permission, wrong scope, non-entitled module → `module_not_entitled`).
3. **Tenant isolation tests** using the shared isolation helpers (`MULTI_TENANT_ARCHITECTURE.md` §8): list, retrieve, update, delete, cross-tenant FK, missing tenant context, Celery task, RLS raw-SQL check.
4. **Validation tests** for serializers and custom field (JSONB) validation.
5. **Financial tests** (fees, accounting, payroll, billing): balanced journals, atomic rollback on failure, idempotency (repeat same key → single effect), concurrency (parallel payments on same invoice do not over-allocate — using threads/transactions on real PostgreSQL), immutability (posted rows cannot be updated), gap-free numbering under concurrency.
6. **Migration tests** for data migrations (forward on representative data).
7. **Frontend tests** for complex components (dynamic forms, permission gating, money display) and E2E for the module's primary flow.

## 3. Automated guards (CI)

- URL-pattern audit: every tenant endpoint declares `ModuleEntitled` + `HasPermission` (or reviewed exemption).
- Model audit: every model with tenant data inherits `TenantScopedModel` and has an RLS policy.
- Import-linter: module dependency rules (`SYSTEM_ARCHITECTURE.md` §4).
- `makemigrations --check`.
- Coverage thresholds: backend services/selectors ≥ 85% lines (proposed), overall backend ≥ 80%; frontend critical libs ≥ 70% (proposed). Thresholds never lowered without ADR.

## 4. Test data

- `factory_boy` factories per model with tenant-aware defaults (`TenantFactory`, `InstitutionFactory(institution_type=...)`).
- Fixtures: `tenant_a`, `tenant_b`, `actor_with_perms([...])`, `api_client_for(actor)`.
- Seed command for local/staging: synthetic tenants for each institution type (school, college, university, madrasa, coaching_center, training_institute) with realistic volumes. **Never real personal data.**
- Time control with `freezegun`; deterministic randomness (seeded).
- External providers (payments, SMS, email, LLM) replaced by fakes in tests; no network calls in CI.

## 5. Conventions

- Backend tests live in `backend/apps/<module>/tests/` (`test_services.py`, `test_api.py`, `test_permissions.py`, `test_isolation.py`); cross-cutting suites in `backend/tests/`.
- Test names describe behavior: `test_teacher_cannot_enter_marks_for_unassigned_offering`.
- Frontend: `*.test.ts(x)` beside sources; E2E in `frontend/e2e/` organized by role.
- Flaky tests are fixed or quarantined with an issue reference within the same PR — never silently retried forever.
- **Tenant-host tests (Phase 3 M3):** tenant hosts are off by default in the test settings too. The `tenant_hosts` / `tenant_site` fixtures switch them on, use the reserved domain `{slug}.tenants.test`, and install probe endpoints (`tests.isolation_app.urls`) that exist only in tests.
- **Durable audit in tests:** `audit_durable` is a real second connection. A test that triggers a durable event lists it in `pytest.mark.django_db(databases=[...])` and reads the events through that alias. Worker-thread tests commit real, append-only audit events, so assertions on audit events must be scoped (by tenant, actor or request), never global counts.
- **Tenant-host E2E (Phase 3 M10):** `frontend/e2e/tenants.spec.ts` runs when `E2E_TENANT_HOSTS=1` against a stack with `TENANT_HOSTS_ENABLED=true` and `CSRF_TRUSTED_ORIGINS` including `http://*.localhost:8080` (CI sets both for its throwaway stack). Tenant hosts are `{slug}.localhost`. Evidence map: `docs/security/PHASE_03_ISOLATION_EVIDENCE.md`.
- **Celery tasks (Phase 3 M7):** every new task is declared with `platform_task` (a catalogued system operation) or `tenant_task`; the declaration test fails otherwise. The test email backend refuses to send inside an open tenant transaction for every test.
- **Real transactions:** commit, rollback, `on_commit` and connection-reuse behaviour are tested in worker threads on unwrapped connections with committed tenants (`committed_tenant_pair`, `committed_tenant_sites`), which the fixtures remove afterwards.

## 6. Commands (implemented in Phase 1 — see `Makefile`)

```bash
make test            # backend + frontend unit/integration
make test-backend    # pytest
make test-frontend   # vitest
make e2e             # playwright against compose
make lint            # ruff + eslint + prettier check
make typecheck       # mypy + tsc
make smoke           # manage.py smoke_check inside the running stack
make schema          # regenerate OpenAPI + TS client
```

**Database role in tests (ADR-009):** pytest creates and migrates `test_erp` as `erp_owner`,
then `backend/conftest.py` switches the connection to `erp_app` for every test.
`apps/core/tests/test_db_roles.py` fails if tests ever run with a privileged role. It also
proves the RLS foundation with a throwaway FORCE-RLS table: fail-closed without context,
transaction-scoped context with no leak, and `WITH CHECK` blocking cross-tenant writes.

## 7. Reporting

Each phase summary includes the exact commands run and their results (pass/fail counts, coverage). Failures are reported honestly, with the output.

### Change notes
- 2026-11-05 — Initial version (Phase 0).
- 2026-11-05 — Phase 1: commands implemented; test-role mechanics documented.
- 2026-11-13 — Phase 3 M3: tenant-host fixtures, durable-audit and real-transaction test conventions.
- 2026-11-18 — Phase 3 M7: task declaration rule and the guarded email backend.
- 2026-11-19 — Phase 3 M10: tenant-host E2E conditions and the evidence map.
