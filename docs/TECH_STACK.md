# Technology Stack

> Mandated by the project owner (see ADR-003). Library choices marked *(proposed)* need approval per `DECISION_LOG.md`.
> Versions are minimums/major lines; exact patch versions are pinned in lockfiles during Phase 1.

## 1. Core stack (mandated)

| Layer | Technology | Version line | Why |
|---|---|---|---|
| Frontend framework | Next.js (App Router) | 16.x | SSR/RSC, routing, mature ecosystem |
| Language (FE) | TypeScript | 5.x, `strict` | Type safety, generated API types |
| Styling | Tailwind CSS | 4.x | Utility-first, design tokens, theming |
| UI components | shadcn/ui (Radix primitives) | latest at Phase 1 | Accessible, owned source, customizable |
| Backend language | Python | 3.13 | Supported by Django 5.2 |
| Backend framework | Django | 5.2 LTS | Long-term support (security fixes to ~April 2028), ORM, admin, migrations |
| API | Django REST Framework | 3.16+ | Serializers, permissions, throttling |
| Database | PostgreSQL | 17 | JSONB, RLS, partitioning, reliability |
| Vector search | pgvector | 0.8+ | Embeddings inside PostgreSQL (no extra DB) |
| Cache / broker | Redis | 7.x (or Valkey-compatible) | Cache, Celery broker, rate limiting |
| Background jobs | Celery (+ Celery beat) | 5.x | Async tasks, scheduled jobs |
| Object storage | S3-compatible API (SeaweedFS 4.50 in dev — ADR-029; managed S3 in prod) | — | Files, documents, exports, backups |
| Containers | Docker, Docker Compose | — | Reproducible environments |
| Reverse proxy | Nginx | stable | TLS termination, static, routing |
| CI/CD | GitHub Actions | — | Integrated with repository |
| Monitoring | Sentry + structured logging | — | Errors, performance, traceability |

## 2. Backend libraries (proposed)

| Purpose | Library | Notes |
|---|---|---|
| OpenAPI schema | `drf-spectacular` | Source of truth for the TS client |
| Browser auth | Django sessions + DRF `SessionAuthentication` (built in) | ADR-011 accepted. `cached_db` session backend (Redis + PostgreSQL) |
| Mobile/third-party auth (future) | `django-oauth-toolkit` or `djangorestframework-simplejwt` | ADR-028 Proposed. **Not** installed until decided |
| UUIDv7 | `uuid-utils` (stdlib-compatible API), fallback `uuid6` | ADR-012 accepted. Pinned. Used only inside `core.ids` |
| Filtering | `django-filter` | |
| CORS | `django-cors-headers` | |
| Settings/env | `django-environ` (or `pydantic-settings`) | Pick one in Phase 1 |
| Storage | `django-storages[s3]` + `boto3` | Any S3-compatible endpoint |
| Logging | `structlog` | JSON logs |
| Error tracking | `sentry-sdk` | |
| Password hashing | `argon2-cffi` | Django Argon2 hasher |
| MFA | `django-otp` (TOTP) / WebAuthn later | Decide in Phase 2 |
| pgvector | `pgvector` (Python) | |
| Server | `gunicorn` + `uvicorn` workers | ASGI-ready |
| Testing | `pytest`, `pytest-django`, `factory_boy`, `pytest-cov`, `freezegun` | |
| Lint/format | `ruff` | Replaces flake8/isort/black |
| Type checking | `mypy` + `django-stubs` + `djangorestframework-stubs` | |
| Security scan | `pip-audit`, `bandit` (via ruff `S` rules) | |
| Package manager | `uv` | ADR-013 (accepted) |

## 3. Frontend libraries (proposed)

| Purpose | Library |
|---|---|
| Server state | TanStack Query |
| Forms | react-hook-form + zod |
| API types | `openapi-typescript` (+ `openapi-fetch`) generated from DRF schema |
| i18n | `next-intl` |
| Tables | TanStack Table |
| Charts | Recharts (via shadcn charts) |
| Icons | lucide-react |
| Dates | date-fns (+ tz support) |
| Unit/component tests | Vitest + Testing Library |
| E2E | Playwright |
| Lint/format | ESLint (flat config) + Prettier |
| Package manager | pnpm workspace (ADR-013, accepted) |

## 4. Explicitly not used (without accepted ADR)

- **MongoDB** or any second primary database (ADR-004).
- GraphQL (REST + OpenAPI is sufficient; revisit only with evidence).
- Microservices / Kubernetes at the start (modular monolith + Compose; ADR-002).
- Separate search engine (Elasticsearch/OpenSearch) — PostgreSQL full-text search first (ADR-018).
- Separate vector DB — pgvector first.

## 5. Dependency policy

1. Every new dependency must be justified in the PR (what problem, alternatives considered, maintenance status, license).
2. Prefer the standard library, Django/DRF built-ins, or an existing dependency.
3. Pin versions via lockfiles (`uv.lock`, `pnpm-lock.yaml`); Dependabot/Renovate for updates.
4. Licenses must be compatible with commercial SaaS (MIT/BSD/Apache-2.0 preferred; no AGPL in the app without approval).

### Change notes
- 2026-11-05 — Initial version (Phase 0).
- 2026-11-05 — Updated for owner-approved ADR-009/010/011/012/013/014 (session auth, transaction-scoped RLS context, DB roles, UUIDv7 abstraction, tenant-level subscription with campus limits, uv/pnpm, layout).

## 6. Pinned versions in use (Phase 1, ADR-030)

| Component | Version |
|---|---|
| Python / Django / DRF | 3.13.18 / 5.2.19 / 3.18.3 |
| drf-spectacular / django-environ / uuid-utils | 0.30.x / 0.14.x / 1.2.0 |
| Celery / redis-py / structlog / sentry-sdk | 5.7.x / 8.x / 26.x / 2.74.x |
| uv | 0.11.32 |
| Node.js / pnpm | 24.22.2 / 10.34.9 |
| Next.js / React / next-intl | 16.4.5 / 19.3.1 / 4.14.9 |
| TypeScript / ESLint | 5.9.3 / 9.39.5 (constraints: ADR-030) |
| Tailwind CSS / Vitest / Playwright | 4.3.4 / 5.1.0 / 1.64.1 |
| openapi-typescript / openapi-fetch | 7.13.0 / 0.17.0 |
| PostgreSQL image | `pgvector/pgvector:0.8.7-pg17` |
| Redis / Nginx / SeaweedFS / Mailpit | `7.4.12-alpine` / `1.28.3-alpine` / `4.50` / `v1.28.4` |

Exact Python and JS versions are locked in `backend/uv.lock` and `pnpm-lock.yaml`.
- 2026-11-05 — Phase 1: updated for the implemented foundation (S3-compatible SeaweedFS dev storage per ADR-029, pinned toolchain per ADR-030).
