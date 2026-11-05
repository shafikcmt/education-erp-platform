# education-erp-platform

**Education ERP — Global Multi-Tenant Configurable Education Management SaaS**

One codebase that runs Schools, Colleges, Universities, Madrasas, Coaching Centers and Training Institutes — configured per institution type and per tenant, never forked.

> **Status:** Phase 0 — documentation and architecture baseline. No application code yet.
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
| Storage | S3-compatible object storage / MinIO |
| Infrastructure | Docker, Docker Compose, Nginx |
| CI/CD | GitHub Actions |
| Monitoring | Sentry, structured logging |

Details: [`docs/TECH_STACK.md`](docs/TECH_STACK.md).

## Repository layout (planned)

```
CLAUDE.md            Permanent instructions for Claude Code sessions
docs/                Project documentation
backend/             Django project (created in Phase 1)
frontend/            Next.js app (created in Phase 1)
packages/api-client/ Generated TypeScript API client (Phase 1+)
infra/               Docker, Nginx, scripts (Phase 1)
.github/workflows/   CI/CD (Phase 1)
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

Not available yet — the development environment (`docker compose up`) is delivered in **Phase 1**. This section will be updated then.

## Contributing

- Never commit directly to `main`; use feature branches and pull requests.
- Follow [`CLAUDE.md`](CLAUDE.md) §16 (coding standards and GitHub workflow).
- Never commit secrets or personal data.
