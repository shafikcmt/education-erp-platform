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
| Object storage | S3-compatible / MinIO | — | Files, documents, exports, backups |
| Containers | Docker, Docker Compose | — | Reproducible environments |
| Reverse proxy | Nginx | stable | TLS termination, static, routing |
| CI/CD | GitHub Actions | — | Integrated with repository |
| Monitoring | Sentry + structured logging | — | Errors, performance, traceability |

## 2. Backend libraries (proposed)

| Purpose | Library | Notes |
|---|---|---|
| OpenAPI schema | `drf-spectacular` | Source of truth for the TS client |
| Auth tokens | `djangorestframework-simplejwt` | Only if ADR-011 (JWT via BFF) is accepted |
| Filtering | `django-filter` | |
| CORS | `django-cors-headers` | |
| Settings/env | `django-environ` (or `pydantic-settings`) | Pick one in Phase 1 |
| Storage | `django-storages[s3]` + `boto3` | S3/MinIO |
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
| Package manager | `uv` | ADR-013 |

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
| Package manager | pnpm (ADR-013) |

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
