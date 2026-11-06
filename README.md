# education-erp-platform

**Education ERP — Global Multi-Tenant Configurable Education Management SaaS**

One codebase that runs Schools, Colleges, Universities, Madrasas, Coaching Centers and Training Institutes — configured per institution type and per tenant, never forked.

> **Status:** Phase 1 — repository foundation & infrastructure implemented (PR awaiting approval). No business modules yet.
> See [`docs/DEVELOPMENT_PROGRESS.md`](docs/DEVELOPMENT_PROGRESS.md) for live status.

---

## What this platform is

- **Multi-tenant SaaS:** `Platform → Tenant → Institution → Campus`, with strict server-side tenant isolation.
- **Configurable:** three customization levels — shared core modules (L1), institution-type presets (L2), tenant-specific declarative extensions via the Customization Studio (L3).
- **Modular:** academics, admissions, students, staff, attendance, examinations, fees, accounting, HR & payroll, hostel, transport, library, LMS, online exams, communication, reports & analytics, AI assistant — sold through subscription plans and paid add-ons.
- **Secure by design:** RBAC with scoped permissions, audit logging, financial integrity, encrypted backups.

## Technology stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, TypeScript, Tailwind CSS, shadcn/ui |
| Backend | Python 3.13, Django 5.2 LTS, Django REST Framework |
| Database | PostgreSQL 17 (JSONB, pgvector) |
| Async & cache | Redis, Celery |
| Storage | S3-compatible object storage (SeaweedFS in dev; managed S3 in production) |
| Infrastructure | Docker, Docker Compose, Nginx |
| CI/CD | GitHub Actions |
| Monitoring | Sentry, structured logging |

Details: [`docs/TECH_STACK.md`](docs/TECH_STACK.md).

## Repository layout

```
CLAUDE.md            Permanent instructions for Claude Code sessions
docs/                Project documentation (plans in docs/plans/)
backend/             Django 5.2 project — config/ (settings dev/test/prod), apps/<module>/
frontend/            Next.js 16 app — src/app/[locale], i18n (en, bn), generated API client
packages/api-client/ OpenAPI schema + generated TypeScript types (do not edit by hand)
infra/               Postgres role bootstrap, Nginx config, object-storage config
.github/             CI workflow, Dependabot, PR template
docker-compose.yml   Development stack (11 services: 9 long-running + 2 one-shot, pinned images)
Makefile             Developer commands (`make help`)
```

## Documentation

| Topic | Document |
|---|---|
| Project instructions (start here) | [`CLAUDE.md`](CLAUDE.md) |
| Vision & goals | [`docs/PROJECT_VISION.md`](docs/PROJECT_VISION.md) |
| Requirements | [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) |
| System architecture | [`docs/SYSTEM_ARCHITECTURE.md`](docs/SYSTEM_ARCHITECTURE.md) |
| Tech stack | [`docs/TECH_STACK.md`](docs/TECH_STACK.md) |
| Database design | [`docs/DATABASE_DESIGN.md`](docs/DATABASE_DESIGN.md) |
| ERD | [`docs/ERD.md`](docs/ERD.md) |
| Multi-tenancy | [`docs/MULTI_TENANT_ARCHITECTURE.md`](docs/MULTI_TENANT_ARCHITECTURE.md) |
| Module catalog | [`docs/MODULE_CATALOG.md`](docs/MODULE_CATALOG.md) |
| Customization engine | [`docs/CUSTOMIZATION_ENGINE.md`](docs/CUSTOMIZATION_ENGINE.md) |
| Subscription & billing | [`docs/SUBSCRIPTION_AND_BILLING.md`](docs/SUBSCRIPTION_AND_BILLING.md) |
| Security | [`docs/SECURITY.md`](docs/SECURITY.md) |
| API standards | [`docs/API_STANDARDS.md`](docs/API_STANDARDS.md) |
| Frontend standards | [`docs/FRONTEND_STANDARDS.md`](docs/FRONTEND_STANDARDS.md) |
| AI assistant | [`docs/AI_ASSISTANT.md`](docs/AI_ASSISTANT.md) |
| Docker & deployment | [`docs/DOCKER_DEPLOYMENT.md`](docs/DOCKER_DEPLOYMENT.md) |
| Testing strategy | [`docs/TESTING_STRATEGY.md`](docs/TESTING_STRATEGY.md) |
| Roadmap | [`docs/DEVELOPMENT_ROADMAP.md`](docs/DEVELOPMENT_ROADMAP.md) |
| Progress | [`docs/DEVELOPMENT_PROGRESS.md`](docs/DEVELOPMENT_PROGRESS.md) |
| Decision log | [`docs/DECISION_LOG.md`](docs/DECISION_LOG.md) |
| Phase 1 plan | [`docs/plans/PHASE_01_PLAN.md`](docs/plans/PHASE_01_PLAN.md) |

## Quick start

**Prerequisites:** Docker with Compose v2. For running tools on the host: Python 3.13 + [uv](https://docs.astral.sh/uv/), Node.js 24 LTS (`.nvmrc`) + pnpm via Corepack.

```bash
cp .env.example .env            # dummy local values only
docker compose up -d --build --wait
```

| URL | What |
|---|---|
| http://localhost:8080 | App through Nginx (single origin): `/` → Next.js, `/api/` → Django |
| http://localhost:8080/en/system | System status page (calls the API through the generated client) |
| http://localhost:8080/api/docs/ | OpenAPI docs (dev only) |
| http://localhost:8080/healthz, `/readyz` | Liveness / readiness probes |
| http://localhost:8025 | Mailpit (captured dev email) |
| http://localhost:8080/en/login | Sign-in (English; `/bn/login` for Bengali) |

Create the first platform Super Admin (no default credentials; the activation link arrives in Mailpit, and MFA enrollment is required on first sign-in):

```bash
docker compose exec api python manage.py create_platform_admin --email owner@example.test
```

```bash
make smoke          # DB role, Redis, object storage and Celery round-trip inside the stack
make s3-check       # S3 compatibility + bucket isolation suite against the object store
make test           # backend (pytest on PostgreSQL as erp_app) + frontend (Vitest)
make lint typecheck # ruff, import contracts, ESLint, Prettier, mypy, tsc
make e2e            # Playwright against a fresh stack (bootstraps the E2E admin)
make schema         # regenerate OpenAPI + TypeScript client after API changes
```

Backend tests on the host need the compose `postgres` running (port 5432 on localhost).
For frontend hot reload, run `pnpm --filter @erp/frontend dev` on the host (port 3000).

## Contributing

- Never commit directly to `main`; use feature branches and pull requests.
- Follow [`CLAUDE.md`](CLAUDE.md) §16 (coding standards and GitHub workflow).
- Never commit secrets or personal data.
