# Phase 1 Implementation Plan — Repository Foundation & Infrastructure

- **Status:** **Approved** by owner 2026-11-05 (with ADR-015, ADR-021 and Q2–Q8 decisions). Implemented on branch `feat/phase-01-foundation`; see §13 for outcome and deviations.
- **Prepared:** 2026-11-05
- **Roadmap reference:** `DEVELOPMENT_ROADMAP.md` → Phase 1
- **Governing decisions:**
  - Accepted: ADR-001–008 (mandates), ADR-009 (tenancy), ADR-011 (session auth), ADR-012 (UUIDv7), ADR-013 (uv/pnpm), ADR-014 (layout).
  - Approval requested with this plan: ADR-015 (REST + OpenAPI + generated TS client) and ADR-021 (en/bn i18n). Phase 1 scaffolds both.

## 1. Goal

Deliver a reproducible, secure-by-default monorepo foundation:
- `docker compose up` produces a healthy full stack.
- CI enforces lint, format, types, tests, migrations, schema drift, image builds and secret scanning.
- The platform primitives every later phase depends on exist: UUIDv7 ids, error format, request IDs, structured logging, health checks, Celery, storage, DB roles, i18n shell.

**No business features:** no tenants, login flows, RBAC, dashboards or domain models.

## 2. Prerequisites checklist

| Item | State |
|---|---|
| Phase 0 docs reviewed by owner | Done (ADR approvals 2026-11-05) |
| Phase 0 PR merged into `main` | **Pending owner** (Phase 1 branch will start from updated `main`) |
| ADR-012 / 013 / 014 | Accepted |
| ADR-015 / ADR-021 | Approval requested with this plan |
| Open questions in §11 answered | Pending owner |
| Branch protection on `main` | Pending owner (GitHub settings) |

## 3. Scope

### In scope
1. Monorepo tooling: root `package.json` (pnpm workspace + `packageManager` pin), `pnpm-workspace.yaml`, `Makefile`, `.editorconfig`, `.gitignore`, `.gitattributes`, `.env.example`, `.pre-commit-config.yaml`.
2. **Backend** (`backend/`):
   - Django 5.2 LTS project; split settings `base/dev/test/prod`; env-driven config.
   - DRF; drf-spectacular (`/api/schema/`, `/api/docs/` in non-prod).
   - `core` app with:
     - `core.ids.new_id()` (UUIDv7, ADR-012);
     - abstract `BaseModel` (id, created_at, updated_at; **no concrete tables**);
     - RFC 9457 problem-details exception handler;
     - pagination classes;
     - `RequestIDMiddleware`;
     - structlog configuration (JSON in prod, console in dev; PII-redaction processor);
     - `/healthz` (liveness) and `/readyz` (DB, Redis, storage checks).
   - Sentry init when `SENTRY_DSN` is set (`send_default_pii=False`).
   - Celery app + beat; `core.ping` task; queue definitions (`default`, `notifications`, `reports`, `imports`, `finance`, `ai`).
   - `django-storages` S3 backend pointed at MinIO.
   - Security settings baseline (secure cookies, HSTS in prod, `SESSION_COOKIE_HTTPONLY`, `SameSite=Lax`, host-only cookies, CSRF config per ADR-011 — the configuration only, auth endpoints come in Phase 2).
   - Postgres extensions migration (`vector`, `pg_trgm`, `btree_gist`, `citext`).
   - Management command `export_openapi`.
   - import-linter contracts (module layering, "only `core.ids` imports the UUID library").
3. **Database roles (ADR-009 foundation):**
   - A Postgres init script creates `erp_owner` (owns schema, runs migrations), `erp_app` (runtime, `NOSUPERUSER NOBYPASSRLS`, DML grants via default privileges) and `erp_platform` (reserved `BYPASSRLS`, unused until Phase 3).
   - The app and tests connect as `erp_app`; `migrate` runs with `DATABASE_MIGRATION_URL` (`erp_owner`).
4. **Frontend** (`frontend/`):
   - Next.js 16 App Router; TypeScript strict (+ `noUncheckedIndexedAccess`); Tailwind CSS 4; shadcn/ui initialized (a minimal set of primitives only: button, card, input, label, sonner/toast).
   - next-intl with `[locale]` routing for `en` and `bn` (RTL-ready via logical CSS properties).
   - Fonts via `next/font` (Latin + Bengali).
   - Base layout and a placeholder landing page showing build info, plus a page that calls the API `/healthz` through the generated client (to prove end-to-end wiring).
   - ESLint flat config (Next, TS, jsx-a11y), Prettier, Vitest + Testing Library, Playwright config with smoke tests.
   - `lib/api` wrapper (openapi-fetch, `credentials: 'include'`, CSRF header hook ready for Phase 2).
5. **`packages/api-client/`:** committed `openapi.yaml` + `openapi-typescript`-generated `schema.d.ts`, a `generate` script, and a drift check.
6. **Docker:**
   - `backend/Dockerfile` (multi-stage, uv, non-root, healthcheck); `frontend/Dockerfile` (multi-stage, standalone output, non-root).
   - `docker-compose.yml` dev stack (see §6).
   - `infra/nginx/` dev config giving one origin: `/api/` → api, `/` → web.
   - `infra/docker/postgres/init/` role scripts; `infra/scripts/` (entrypoints, wait-for).
7. **CI** (`.github/workflows/ci.yml`): jobs as in §8. Also `.github/dependabot.yml` (pip/uv, npm/pnpm, docker, github-actions) and `.github/pull_request_template.md` (sections required by `CLAUDE.md` §16).
8. **Docs:** README quick start; `TECH_STACK.md` pinned versions; `DEVELOPMENT_PROGRESS.md`; decision-log entries for Phase 1 library choices (§11).

### Out of scope (explicitly)
- Tenants, RLS policies, `tenant_atomic` (Phase 3). Only DB roles are created now.
- Login/logout/MFA endpoints and UI, RBAC (Phase 2).
- Any domain model, dashboard or module UI.
- Production compose, CD, TLS, backups (Phase 19).

## 4. Dependencies (to be pinned to latest stable at implementation time; each justified)

**Backend runtime:**

| Package | Justification |
|---|---|
| `django~=5.2` | Mandated LTS |
| `djangorestframework` | Mandated API framework |
| `drf-spectacular` | OpenAPI contract (ADR-015) |
| `django-environ` | 12-factor settings (one small dependency; alternative pydantic-settings is heavier) |
| `psycopg[binary,pool]` 3.x | PostgreSQL driver (binary wheels; may switch to source build in prod image) |
| `pgvector` | Vector field/extension support (needed from Phase 16; included now only if the extension migration needs it — otherwise deferred) |
| `redis` | Cache/session/broker client |
| `celery` | Mandated |
| `django-storages[s3]` + `boto3` | S3/MinIO storage |
| `structlog` | Structured logging (mandated) |
| `sentry-sdk[django,celery]` | Monitoring (mandated) |
| `gunicorn` + `uvicorn-worker` | ASGI server in containers |
| `argon2-cffi` | Argon2 hasher configured from day one |
| `uuid-utils` (fallback `uuid6`) | UUIDv7 (ADR-012); maintenance verified before pinning |

**Backend dev:** `ruff`, `mypy`, `django-stubs[compatible-mypy]`, `djangorestframework-stubs`, `pytest`, `pytest-django`, `pytest-cov`, `factory-boy`, `freezegun`, `import-linter`, `pip-audit`.

**Frontend runtime:** `next@16`, `react`, `react-dom`, `next-intl`, `@tanstack/react-query`, `openapi-fetch`, `tailwindcss@4`, shadcn/ui dependencies (`class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, Radix primitives as generated), `zod`, `react-hook-form`.
- `zod` and `react-hook-form` are installed now only if a form exists in Phase 1. Otherwise they are deferred to Phase 2 (default: **defer**).

**Frontend dev:** `typescript`, `eslint` + `eslint-config-next` + `eslint-plugin-jsx-a11y`, `prettier` (+ tailwind plugin), `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `jsdom`, `@playwright/test`, `openapi-typescript`.

**Runtime versions:**
- Python 3.13 (`.python-version`).
- Node 24 LTS (`.nvmrc` + `engines`).
- pnpm pinned via `packageManager`.

## 5. File structure (target at end of Phase 1)

```
.
├── CLAUDE.md
├── README.md
├── docs/ … (existing) + docs/plans/PHASE_01_PLAN.md
├── package.json                  # pnpm workspace root, packageManager pin, scripts
├── pnpm-workspace.yaml           # frontend, packages/*
├── pnpm-lock.yaml
├── Makefile                      # up, down, logs, migrate, test, lint, typecheck, schema, fmt
├── docker-compose.yml
├── .env.example
├── .editorconfig  .gitignore  .gitattributes  .pre-commit-config.yaml  .nvmrc
├── .github/
│   ├── workflows/ci.yml
│   ├── dependabot.yml
│   └── pull_request_template.md
├── backend/
│   ├── pyproject.toml  uv.lock  .python-version  Dockerfile  .dockerignore
│   ├── manage.py
│   ├── importlinter.ini (or [tool.importlinter] in pyproject)
│   ├── config/
│   │   ├── __init__.py           # loads celery app
│   │   ├── settings/{__init__,base,dev,test,prod}.py
│   │   ├── urls.py  asgi.py  wsgi.py  celery.py
│   ├── apps/
│   │   ├── __init__.py
│   │   └── core/
│   │       ├── __init__.py  apps.py
│   │       ├── ids.py            # new_id() — sole UUIDv7 entry point
│   │       ├── models.py         # abstract BaseModel only
│   │       ├── middleware.py     # RequestIDMiddleware
│   │       ├── logging.py        # structlog setup + redaction
│   │       ├── exceptions.py     # problem-details handler + error codes
│   │       ├── pagination.py
│   │       ├── health.py         # /healthz, /readyz views
│   │       ├── tasks.py          # core.ping
│   │       ├── management/commands/export_openapi.py
│   │       ├── migrations/0001_postgres_extensions.py
│   │       └── tests/ (test_ids.py, test_health.py, test_errors.py, test_request_id.py,
│   │                   test_celery.py, test_settings.py, test_db_role.py, test_openapi.py)
│   └── tests/conftest.py
├── frontend/
│   ├── package.json  tsconfig.json  next.config.ts  eslint.config.mjs  .prettierrc
│   ├── vitest.config.ts  playwright.config.ts  components.json  Dockerfile  .dockerignore
│   ├── src/
│   │   ├── app/[locale]/{layout.tsx,page.tsx,system/page.tsx}  app/globals.css
│   │   ├── components/ui/…       # shadcn generated
│   │   ├── i18n/{routing.ts,request.ts}  middleware.ts (or Next 16 proxy.ts)
│   │   ├── lib/api/client.ts     # openapi-fetch wrapper
│   │   └── messages/{en.json,bn.json}
│   ├── src/**/*.test.tsx
│   └── e2e/smoke.spec.ts
├── packages/api-client/
│   ├── package.json  openapi.yaml  src/schema.d.ts  src/index.ts
└── infra/
    ├── docker/postgres/init/01-roles.sh
    ├── nginx/dev.conf
    └── scripts/{api-entrypoint.sh,wait-for.sh}
```

## 6. Docker services (dev `docker-compose.yml`)

| Service | Image / build | Ports (host) | Healthcheck | Notes |
|---|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg17` (pinned tag) | 5432 (optional) | `pg_isready` | Init script creates `erp_owner`, `erp_app`, `erp_platform`; named volume |
| `redis` | `redis:7.4-alpine` (pinned) | — | `redis-cli ping` | Cache, sessions, Celery broker |
| `minio` | `minio/minio` (pinned) | 9001 console | `/minio/health/live` | Dev object storage |
| `minio-init` | `minio/mc` | — | one-shot | Creates bucket + least-privilege app user |
| `mailpit` | `axllent/mailpit` | 8025 UI | built in | Dev email capture |
| `migrate` | backend image | — | one-shot | `manage.py migrate` as `erp_owner`; `api` depends on its completion |
| `api` | `backend/Dockerfile` (dev target) | — | `GET /healthz` | runserver with autoreload in dev; connects as `erp_app` |
| `worker` | backend image | — | `celery inspect ping` | All queues in dev |
| `beat` | backend image | — | — | Single instance |
| `web` | `frontend/Dockerfile` (dev target) | — | `GET /` | `next dev` with bind mount |
| `nginx` | `nginx:stable-alpine` (pinned) | **8080** | `GET /healthz` via proxy | Single origin: `/api/` + `/healthz` + `/readyz` → api, `/` → web (ADR-011 same-origin topology) |

Host access: `http://localhost:8080`. `*.localhost` subdomains resolve locally in modern browsers, ready for tenant subdomains in Phase 3.

## 7. Implementation steps (order)

1. Branch `feat/phase-01-foundation` from updated `main` (or the session-assigned branch).
2. Root tooling files and `.env.example` (dummy values).
3. Backend skeleton with `uv init`, settings, `core` app, ids, error handler, middleware, logging, health, Celery, storage, extensions migration, tests.
4. Postgres role init script + compose services `postgres`, `redis`, `minio`, `mailpit`, `migrate`, `api`, `worker`, `beat`.
5. OpenAPI export → `packages/api-client` generation.
6. Frontend skeleton: Next.js 16, Tailwind 4, shadcn init, next-intl, API wrapper, pages, unit + E2E smoke tests; `web` + `nginx` services.
7. Makefile targets; pre-commit.
8. CI workflow, dependabot, PR template.
9. Run the full verification checklist (§9) locally/in-session and fix everything.
10. Docs update (README quick start, TECH_STACK pins, PROGRESS, DECISION_LOG); open PR; report the real results.

## 8. CI jobs (`.github/workflows/ci.yml`, on pull_request + push to main)

| Job | Commands |
|---|---|
| `backend-quality` | `uv sync --frozen` → `ruff check` → `ruff format --check` → `mypy` → `lint-imports` |
| `backend-test` | services: `pgvector/pgvector:pg17` + `redis`; run role init; `manage.py migrate` (as owner) → `makemigrations --check --dry-run` → `pytest --cov` (as `erp_app`; coverage gate for `apps/core` ≥ 85%) |
| `backend-security` | `pip-audit` (via `uv export`), ruff `S` rules |
| `api-contract` | `manage.py spectacular --validate --fail-on-warn` → regenerate `packages/api-client` → `git diff --exit-code` |
| `frontend-quality` | `pnpm install --frozen-lockfile` → `pnpm -r lint` → `prettier --check` → `pnpm -r typecheck` (`tsc --noEmit`) |
| `frontend-test` | `pnpm --filter frontend test` (Vitest) |
| `e2e-smoke` | `docker compose up -d --wait` → Playwright smoke (en + bn pages render; `/api/healthz` via nginx returns 200) |
| `docker-build` | Build backend + frontend images (no push); Trivy scan (fail on fixable CRITICAL) |
| `secret-scan` | gitleaks |

Path filters keep backend-only or frontend-only PRs fast.

## 9. Acceptance criteria (all must pass)

1. `cp .env.example .env && docker compose up -d --wait` brings every service to **healthy** from a clean checkout. `http://localhost:8080` renders the landing page in `en` and `bn`.
2. `GET /healthz` → 200. `GET /readyz` → 200 when DB, Redis and MinIO are up, and **503 with a problem-details body** when one is down (tested).
3. Error responses follow the problem-details format with `code` and `request_id`. `X-Request-ID` is echoed (generated if absent). Logs are JSON in prod mode and include `request_id`.
4. `core.ids.new_id()` returns `uuid.UUID` with version 7, monotonic ordering, and is the only UUID-library import in the codebase (import-linter enforced).
5. The API process and the test suite connect as `erp_app`. A test asserts the current role is not a superuser and has `rolbypassrls = false`. Migrations run as `erp_owner`.
6. Extensions `vector`, `pg_trgm`, `btree_gist` and `citext` are installed by migration.
7. A Celery `core.ping` task round-trips through Redis in the compose stack; beat starts without errors.
8. File upload/download smoke against MinIO via `django-storages` (test with the storage backend).
9. OpenAPI schema validates with zero warnings. The generated TS client is committed, with no drift. The frontend system page calls `/api/healthz` through the generated client.
10. Security baseline settings are verified by tests in `prod` settings mode: `DEBUG=False`, secret key required, HSTS, secure + HttpOnly + SameSite=Lax session cookie, no `SESSION_COOKIE_DOMAIN`, Argon2 first hasher.
11. All CI jobs green on the PR.
12. No secrets committed (gitleaks clean). `.env.example` contains dummy values only.
13. README quick start works exactly as written. Docs and progress are updated.

## 10. Testing checklist

**Backend (pytest, PostgreSQL 17, as `erp_app`):**
- [ ] `test_ids`: version 7, `uuid.UUID` type, 10k ids strictly increasing, uniqueness
- [ ] `test_health`: liveness 200; readiness 200/503 with each dependency mocked down
- [ ] `test_errors`: validation → 400 problem details; 404; unhandled → 500 without stack trace; `request_id` present
- [ ] `test_request_id`: incoming header honored (validated format), generated otherwise, bound into the log context
- [ ] `test_settings`: prod settings security assertions (criterion 10)
- [ ] `test_db_role`: non-superuser, `NOBYPASSRLS`, extensions present
- [ ] `test_celery`: ping task (eager unit + integration marker for the compose run)
- [ ] `test_storage`: save/open/delete roundtrip (MinIO in CI integration; in-memory for unit)
- [ ] `test_openapi`: schema generation without warnings
- [ ] `makemigrations --check` clean
- [ ] ruff, ruff format, mypy (strict for `apps/core`), import-linter, pip-audit

**Frontend:**
- [ ] Vitest: locale switch renders translated strings; API wrapper sends `credentials: 'include'` and attaches CSRF header on unsafe methods (unit-tested with mocked fetch)
- [ ] ESLint, Prettier, `tsc --noEmit` clean
- [ ] Playwright smoke: `/en` and `/bn` render; system page shows API healthy; no console errors; basic axe check on the landing page

**Infrastructure:**
- [ ] `docker compose config` valid; all images build; containers run as non-root
- [ ] `docker compose up --wait` healthy from scratch; `down -v && up` repeatable
- [ ] Trivy: no fixable CRITICAL vulnerabilities
- [ ] gitleaks clean

Results will be reported with the actual command output summaries.

## 11. Decisions needed from owner before/with approval

| # | Question | Recommendation |
|---|---|---|
| Q1 | Approve ADR-015 (REST + OpenAPI + generated TS client) and ADR-021 (en + bn, RTL-ready) since Phase 1 scaffolds them? | Approve |
| Q2 | Create a **minimal custom User model** (`identity.User`: UUIDv7 id, email (citext, unique), password, is_active, is_staff, timestamps) in Phase 1 with `AUTH_USER_MODEL` set? Django strongly recommends setting a custom user model before the first migration; changing it later is very costly. No login flows: those stay in Phase 2. | **Yes**, a stub only |
| Q3 | UUIDv7 library: `uuid-utils` (Rust-backed, stdlib-compatible API) vs `uuid6` (pure Python) | `uuid-utils`, after a maintenance check |
| Q4 | Settings library: `django-environ` vs `pydantic-settings` | `django-environ` |
| Q5 | Node.js runtime: Node 24 LTS | Node 24 LTS |
| Q6 | Nginx included in the dev stack by default (single origin on :8080, mirrors production cookie topology) | Yes |
| Q7 | Redis image: `redis:7.4` (as documented) vs Valkey (BSD-licensed, Redis-compatible). Redis source-available licensing is fine for internal use, but should be noted. | Keep Redis 7.4 now; revisit at Phase 19 |
| Q8 | Merge the Phase 0 PR first, then branch Phase 1 from `main` | Yes |

## 12. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Next.js 16 / Tailwind 4 / shadcn compatibility churn | Pin exact versions; use official init commands; smoke tests in CI |
| RLS tests meaningless if tests run as superuser | `erp_app` role enforced and asserted from Phase 1 |
| Custom user model introduced late | Q2: stub in Phase 1 |
| CI duration | Path filters, uv/pnpm caching, Docker layer caching |
| Network-restricted environments blocking image pulls or registries | Document; retry; fall back to local verification and report honestly |

## 13. Implementation outcome and deviations (2026-11-05)

The plan above is kept as approved. The implementation differs from it in these points, each
recorded in `DECISION_LOG.md`:

| # | Plan said | Implemented | Why | Record |
|---|---|---|---|---|
| D1 | `minio` + `minio-init` (`minio/minio`, `minio/mc`) | `objectstore` + `objectstore-init` using SeaweedFS 4.50 (S3 API) | MinIO community images are no longer available (pull "not found"); ADR-003 allows any S3-compatible store; the app uses only the S3 API | ADR-029 (Proposed, safe default) |
| D2 | Custom `export_openapi` command | drf-spectacular's built-in `manage.py spectacular --validate --fail-on-warn` (wrapped by `make schema` and CI) | Avoids duplicating an existing, maintained command | — |
| D3 | Redis service in the `backend-test` CI job | Not used | Tests use locmem cache and in-memory Celery; Redis is exercised in `e2e-smoke` (`smoke_check`) | — |
| D4 | TanStack Query (and optionally zod/react-hook-form) in Phase 1 | Deferred to Phase 2 | No Phase 1 code uses them (dependency policy) | ADR-030 |
| D5 | TypeScript/ESLint "latest" | TypeScript 5.9.3, ESLint 9.39.5 | Peer constraints of typescript-eslint, openapi-typescript and eslint-config-next plugins | ADR-030 |
| D6 | `nginx:stable-alpine` | `nginx:1.28.3-alpine` running as uid 101 on :8080 | Exact pin + non-root (unprivileged variant unavailable) | ADR-030 |
| D7 | `apps/core/tests/test_storage.py` | Storage covered by `test_health.py` (S3 HeadBucket check) and `smoke_check` (real write/read/delete in the stack) | Unit tests use in-memory storage; a real round-trip only makes sense against the running stack | — |
| D8 | — (addition) | `manage.py smoke_check` and an `/api/` catch-all 404 | Single command proves DB role/cache/storage/Celery in the stack; the error format stays the same with `DEBUG=True` | — |
| D9 | — (addition) | Production images strip system pip/setuptools and npm/corepack | They carried fixable HIGH CVEs found by Trivy; both images are now Trivy-clean | — |

**Acceptance criteria (§9):** criteria 1–10, 12 and 13 were verified in this environment (see
`DEVELOPMENT_PROGRESS.md`). Criterion 11 (all CI jobs green on the PR) can only be confirmed by
GitHub Actions on the PR.

### Change notes
- 2026-11-05 — Initial plan drafted (awaiting approval).
- 2026-11-05 — Status set to Approved; §13 implementation outcome and deviations added.
