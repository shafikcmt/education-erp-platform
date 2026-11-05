# Docker Deployment and CI/CD

> Phase 1 delivers the **development** Compose stack and baseline CI. Phase 19 delivers **production** deployment and CD.
> Hosting provider and region are **not decided** (ADR-019).

## 1. Services

| Service | Image (proposed) | Purpose | Dev | Prod |
|---|---|---|---|---|
| `nginx` | `nginx:stable-alpine` + config | TLS, routing, headers, limits | optional | yes |
| `web` | `frontend/Dockerfile` (Node LTS, multi-stage, Next.js standalone output) | UI + BFF | yes | yes |
| `api` | `backend/Dockerfile` (python:3.13-slim, multi-stage, `uv`) | Django API (Gunicorn + Uvicorn workers) | yes (runserver) | yes |
| `worker` | same image as `api` | Celery workers (queues: default, notifications, reports, imports, finance, ai) | yes | yes (scaled) |
| `beat` | same image as `api` | Celery beat (single instance) | yes | yes (1 replica) |
| `postgres` | `pgvector/pgvector:pg17` | Database | yes | managed DB preferred (with pgvector) or hardened container |
| `redis` | `redis:7-alpine` | Cache/broker | yes | managed or hardened container |
| `minio` | `minio/minio` | S3-compatible storage | yes | managed S3 preferred |
| `mailpit` | `axllent/mailpit` | Dev email capture | yes | no |

Image tags are pinned (and digests in production) during Phase 1/19.

## 2. Repository files (planned)

```
docker-compose.yml               dev stack
docker-compose.prod.yml          production overrides (Phase 19)
.env.example                     documented variables, dummy values only
backend/Dockerfile
frontend/Dockerfile
infra/nginx/nginx.conf, conf.d/*.conf
infra/scripts/                   entrypoints, wait-for, backup/restore helpers
.github/workflows/ci.yml         PR checks
.github/workflows/cd.yml         build/push/deploy (Phase 19)
```

## 3. Image standards

- Multi-stage builds; final images contain only runtime artefacts.
- Run as **non-root** user; read-only root filesystem where possible.
- `HEALTHCHECK` for `api` (`/healthz`), `web`, workers (Celery ping).
- No secrets baked into images; config via env at runtime.
- Reproducible: lockfiles (`uv.lock`, `pnpm-lock.yaml`) copied before source for layer caching.
- Images scanned (e.g. Trivy) in CI; build fails on critical vulnerabilities with available fixes.

## 4. Environments

| Env | Purpose | Deploy trigger | Data |
|---|---|---|---|
| `local` | Developer machine / Claude sessions | `docker compose up` | Synthetic seed data |
| `ci` | Automated tests | Every PR | Ephemeral |
| `staging` | Pre-production verification | Merge to `main` | Synthetic/anonymized only |
| `production` | Customers | Tagged release `vX.Y.Z` + manual approval (GitHub Environment protection) | Real |

## 5. Configuration (environment variables — names illustrative)

`DJANGO_SETTINGS_MODULE`, `DJANGO_SECRET_KEY`, `DATABASE_URL`, `DATABASE_APP_ROLE`, `REDIS_URL`, `CELERY_BROKER_URL`, `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `ALLOWED_HOSTS`, `PLATFORM_DOMAIN`, `CORS_ALLOWED_ORIGINS`, `EMAIL_*`, `FIELD_ENCRYPTION_KEYS`, `LLM_PROVIDER`, `LLM_API_KEY`, `NEXT_PUBLIC_*` (non-secret only).

`.env.example` contains **dummy values only**. Real values never enter git.

## 6. CI pipeline (GitHub Actions, Phase 1 baseline, extended each phase)

On every pull request:

| Job | Steps |
|---|---|
| `backend-lint` | `ruff check`, `ruff format --check`, `mypy` |
| `backend-test` | Postgres 17 + pgvector and Redis service containers → `pytest --cov` (fail under threshold), migrations applied from scratch, `makemigrations --check --dry-run` |
| `backend-security` | `pip-audit`, ruff `S` rules |
| `api-schema` | Generate OpenAPI (fail on warnings); regenerate TS client and fail on diff |
| `frontend-lint` | `pnpm lint`, `prettier --check`, `tsc --noEmit` |
| `frontend-test` | `vitest run` |
| `e2e` (from Phase 2+) | Compose stack up → Playwright critical flows |
| `docker-build` | Build all images (no push); Trivy scan |
| `secrets` | gitleaks / GitHub secret scanning |

Branch protection on `main` (owner to configure): required checks green, ≥1 approving review, no force push, linear history (squash merge recommended).

## 7. CD pipeline (Phase 19)

1. Merge to `main` → build images tagged with commit SHA → push to registry (GHCR proposed) → deploy to staging → run smoke tests + migrations check.
2. Release tag `vX.Y.Z` → promote same images (no rebuild) → production deploy after manual approval.
3. Deploy steps: backup checkpoint → run migrations (backward-compatible only) → rolling restart `api`/`worker`/`web` → health checks → smoke tests → automatic rollback of app containers on failure (DB migrations are forward-only; rollback strategy = expand/contract).
4. Sentry release + source maps uploaded; deploy recorded in progress/ops log.

## 8. Nginx (production)

- TLS (Let's Encrypt via certbot or provider-managed certificates); HSTS; HTTP→HTTPS redirect.
- Routing: `/api/`, `/api/webhooks/`, `/healthz` → `api`; everything else → `web`.
- Security headers (CSP coordinated with Next.js nonces), `client_max_body_size` per route, gzip/brotli, rate limiting zones for auth/public endpoints.
- **Tenant custom domains** require on-demand certificate issuance; plain Nginx + certbot does not handle this well at scale — options (Caddy on-demand TLS in front, a managed edge/CDN, or a cert-manager process) are an open decision (ADR-027).

## 9. Backups (operational)

- Postgres: base backups + WAL archiving with pgBackRest or WAL-G (decision Phase 19) to off-site encrypted storage; retention policy (proposed: daily for 30 days, monthly for 12 months — TBD).
- MinIO/S3: versioning and lifecycle rules; replication for production.
- Restore runbook in `infra/` + quarterly restore drill with recorded results.

## 10. Observability

- Sentry SDKs in `api`, `worker`, `web`; environment + release tags; PII scrubbing.
- structlog JSON to stdout → log collector (choice Phase 19).
- Health: `/healthz` (process alive), `/readyz` (DB, Redis, storage reachable).
- Metrics (proposed): Prometheus-compatible exporter for API latency, Celery queue depth, DB connections; uptime monitor for public endpoints; alert routing (email/Slack — TBD).

### Change notes
- 2026-11-05 — Initial version (Phase 0).
