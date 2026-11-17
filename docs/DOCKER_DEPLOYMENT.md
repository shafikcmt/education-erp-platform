# Docker Deployment and CI/CD

> Phase 1 delivers the **development** Compose stack and baseline CI. Phase 19 delivers **production** deployment and CD.
> Hosting provider and region are **not decided** (ADR-019).

## 1. Services (implemented in Phase 1 — dev stack `docker-compose.yml`)

| Service | Image (pinned) | Purpose | Dev | Prod (Phase 19) |
|---|---|---|---|---|
| `nginx` | `nginx:1.28.3-alpine`, non-root uid 101, port 8080, read-only rootfs | Single origin: `/api/`, `/healthz`, `/readyz` → api; `/` → web; security headers, request IDs, rate limit | yes | yes (+TLS) |
| `web` | `frontend/Dockerfile` target `runtime` (`node:24.22.2-alpine`, Next.js standalone, uid 1000) | UI (SSR); forwards session cookie, holds no credentials | yes | yes |
| `api` | `backend/Dockerfile` target `dev` (runserver, code bind-mounted read-only) / `runtime` (gunicorn + uvicorn-worker) | Django API, connects as `erp_app` | yes | yes |
| `worker` | same image as `api` | Celery worker, queues `default,notifications,reports,imports,finance,ai` | yes | yes (scaled) |
| `beat` | same image as `api` | Celery beat (single instance; schedule file in `/tmp`) | yes | yes (1 replica) |
| `migrate` | same image as `api` (one-shot) | `manage.py migrate` as **`erp_owner`**; `api`/`worker` start only after it succeeds | yes | yes (deploy step) |
| `postgres` | `pgvector/pgvector:0.8.7-pg17` | PostgreSQL 17 + pgvector; `infra/docker/postgres/init/01-roles.sh` creates roles/extensions | yes | managed DB preferred (with pgvector) |
| `redis` | `redis:7.4.12-alpine` (no persistence) | Cache, sessions, Celery broker/results | yes | managed or hardened |
| `objectstore` | `chrislusf/seaweedfs:4.50` (`weed server -s3`) | S3-compatible storage (ADR-029); least-privilege identity rendered from `.env` | yes | managed S3 preferred |
| `objectstore-init` | same image (one-shot) | Idempotently creates the bucket | yes | n/a |
| `mailpit` | `axllent/mailpit:v1.28.4` | Dev email capture (UI :8025) | yes | no |

**11 services: 9 long-running + 2 one-shot (`migrate`, `objectstore-init`).** All app containers (`api`, `worker`, `beat`, `migrate`, `web`, `nginx`) run as **non-root** with a **read-only root filesystem** (tmpfs for `/tmp`). Host ports bind to `127.0.0.1` only.

## 2. Repository files

```
docker-compose.yml                       dev stack (Phase 1)
.env.example                             documented variables, dummy values only
backend/Dockerfile                       targets: dev, runtime
backend/infra-build-ca.sh                optional build-time CA helper (see §3)
frontend/Dockerfile                      targets: deps, builder, runtime (context = repo root)
.dockerignore                            root context (frontend build)
infra/docker/postgres/init/01-roles.sh   roles + extensions bootstrap (also used by CI)
infra/docker/objectstore/                SeaweedFS entrypoint + S3 identity template
infra/nginx/nginx.conf                   single-origin reverse proxy
.github/workflows/ci.yml                 PR checks (Phase 1)
docker-compose.prod.yml, cd.yml          production overrides + CD (Phase 19)
```

## 3. Image standards

- Multi-stage builds; final images contain only runtime artefacts.
- Run as **non-root** user; read-only root filesystem where possible.
- `HEALTHCHECK` for `api` (`/healthz`), `web`, workers (Celery ping).
- No secrets baked into images; config via env at runtime.
- Reproducible: lockfiles (`uv.lock`, `pnpm-lock.yaml`) copied before source for layer caching.
- Images scanned with Trivy in CI; the build fails on **fixable HIGH or CRITICAL** vulnerabilities.
- Production stages remove tooling that is not needed at runtime (system pip/setuptools in the Python image; npm/corepack in the Node image). These carried vendored CVEs, and removing them made both images Trivy-clean in Phase 1.
- **TLS-intercepting proxies (optional):** both Dockerfiles accept a BuildKit secret `build_ca` (extra CA bundle) that is used only during dependency installation and never written to a layer. Example: `docker buildx build --secret id=build_ca,src=/path/ca.crt ...`. Without the secret the build is unchanged.

## 4. Environments

| Env | Purpose | Deploy trigger | Data |
|---|---|---|---|
| `local` | Developer machine / Claude sessions | `docker compose up` | Synthetic seed data |
| `ci` | Automated tests | Every PR | Ephemeral |
| `staging` | Pre-production verification | Merge to `main` | Synthetic/anonymized only |
| `production` | Customers | Tagged release `vX.Y.Z` + manual approval (GitHub Environment protection) | Real |

## 5. Configuration (environment variables — names illustrative)

`DJANGO_SETTINGS_MODULE`, `DJANGO_SECRET_KEY`, `DATABASE_URL` (runtime role `erp_app`, NOBYPASSRLS), `DATABASE_MIGRATION_URL` (owner role `erp_owner`, migrations only), `REDIS_URL`, `CELERY_BROKER_URL`, `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `ALLOWED_HOSTS`, `PLATFORM_DOMAIN`, `CORS_ALLOWED_ORIGINS`, `EMAIL_*`, `FIELD_ENCRYPTION_KEYS`, `LLM_PROVIDER`, `LLM_API_KEY`, `NEXT_PUBLIC_*` (non-secret only).

**Host policy and connections (Phase 3 M3):**

| Variable | Dev / CI default | Production |
|---|---|---|
| `PLATFORM_HOSTS` | `localhost,127.0.0.1,api` (`api` is the internal host the Next.js server calls) | **Required.** Exact platform hosts, each covered by `DJANGO_ALLOWED_HOSTS`; include the internal API host used by the web service |
| `TENANT_BASE_DOMAIN` | `localhost` (tenant hosts would be `{slug}.localhost`) | Empty until the owner provides the domain (D1) |
| `TENANT_HOSTS_ENABLED` | `false` | **`false`.** `true` is refused without a real base domain; enabling it also needs the approved security review |
| `DATABASE_CONN_MAX_AGE` | `0` | Must be `0` (settings refuse anything else, D4). The override exists only for non-production measurements |

The API service must be reachable only through Nginx and the web service: Django trusts the proxy headers they set (`SECURITY.md` §6a).

`.env.example` contains **dummy values only**. Real values never enter git.

## 6. CI pipeline (GitHub Actions — `.github/workflows/ci.yml`, implemented in Phase 1)

On every pull request and on pushes to `main`:

| Job | Steps |
|---|---|
| `backend-quality` | `uv sync --frozen` → `ruff check` → `ruff format --check` → `mypy` (strict) → `lint-imports` |
| `backend-test` | PostgreSQL 17 + pgvector service → `01-roles.sh` bootstrap → `makemigrations --check --dry-run` → `pytest --cov --cov-fail-under=85` (DB created as `erp_owner`, tests run as `erp_app`). Redis is not needed: tests use locmem cache and in-memory Celery. |
| `backend-security` | `pip-audit --strict` on the exported lockfile; ruff `S` rules run in `backend-quality` |
| `api-contract` | `spectacular --validate --fail-on-warn` → `openapi-typescript` → `git diff --exit-code packages/api-client` |
| `frontend-quality` | `pnpm install --frozen-lockfile` → Prettier check → ESLint (`--max-warnings=0`) → `tsc --noEmit` → Vitest → `next build` |
| `e2e-smoke` | `docker compose up -d --build --wait` → `manage.py smoke_check` → S3 compatibility + bucket-isolation suite (`S3_INTEGRATION=1`, ADR-029) → Playwright (desktop + mobile Chromium, incl. axe) |
| `docker-build` | Build production images (`runtime` targets) → Trivy (fail on fixable HIGH/CRITICAL) |
| `secret-scan` | gitleaks over the full git history |

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
- Object storage (S3-compatible): versioning and lifecycle rules; replication for production.
- **Provider-agnostic object backup/restore/migration (implemented in Phase 1):** `manage.py s3_mirror`.
  - `--to-dir DIR`: backup to a directory, with a `manifest.json` of SHA-256 hashes, sizes and content types.
  - `--from-dir DIR`: restore into the app bucket. Every object is verified, and a corrupted backup is rejected.
  - `--to-endpoint/--to-bucket/--to-access-key-env/--to-secret-key-env`: migrate to another S3-compatible provider. Credentials are passed by environment-variable *name*, never on the command line.
  - **Restore order:** provision the empty bucket first (`objectstore-init` or the provider's IaC/console); the app identity cannot create buckets.
  - Verified 2026-11-05: the volume was destroyed, then restored byte-identical; migration SeaweedFS → RustFS. Production schedule, retention and the off-site target are set in Phase 19.
- Restore runbook in `infra/` + quarterly restore drill with recorded results.

## 10. Observability

- Sentry SDKs in `api`, `worker`, `web`; environment + release tags; PII scrubbing.
- structlog JSON to stdout → log collector (choice Phase 19).
- Health: `/healthz` (process alive), `/readyz` (DB, Redis, storage reachable).
- Metrics (proposed): Prometheus-compatible exporter for API latency, Celery queue depth, DB connections; uptime monitor for public endpoints; alert routing (email/Slack — TBD).

### Change notes
- 2026-11-05 — Initial version (Phase 0).
- 2026-11-05 — Updated for owner-approved ADR-009/010/011/012/013/014 (session auth, transaction-scoped RLS context, DB roles, UUIDv7 abstraction, tenant-level subscription with campus limits, uv/pnpm, layout).
- 2026-11-05 — Phase 1: services, files, image standards and CI sections updated to the implemented state (SeaweedFS per ADR-029; pins per ADR-030).
- 2026-11-05 — Phase 1 review: S3 integration step in CI; `s3_mirror` backup/restore/migration documented; service count stated explicitly (11).
- 2026-11-06 — Phase 2:
  - `migrate` now also runs `seed_roles` (permission registry + system roles, as `erp_app`).
  - Nginx overwrites `X-Real-IP`; the API trusts only that header for client IPs (`CLIENT_IP_HEADER`).
  - New variables: `FIELD_ENCRYPTION_KEYS`, `IP_INDEX_KEY` (mandatory in production; real keys only), `FRONTEND_BASE_URL`, `MFA_ISSUER`, `SECURITY_IP_RETENTION_DAYS`, `SECURITY_NOTIFY_NEW_SIGNIN`, `SECURITY_LOGIN_IP_LIMIT`, `PASSWORD_BREACH_CHECK_*`.
  - Celery beat runs `audit.anonymize_expired_ips` and `identity.housekeeping` daily; security emails use the `notifications` queue.
  - CI stack job bootstraps the E2E Super Admin with `create_platform_admin` before Playwright.
- 2026-11-06 — Security review (ADR-040):
  - no service uses `env_file`; each gets an explicit environment allow-list. Runtime services (`api`, `worker`, `beat`, `web`) never receive `DATABASE_MIGRATION_URL`, `ERP_OWNER_PASSWORD` or `POSTGRES_PASSWORD`; `migrate` alone gets the owner URL (`ERP_PROCESS_ROLE=migrate`), `postgres` alone the bootstrap passwords;
  - Django refuses to start a runtime process that holds owner/superuser credentials;
  - CI: `docker compose config --format json | python3 infra/scripts/check_runtime_secrets.py`, plus a check inside the running containers;
  - owner-only maintenance: `docker compose run --rm --entrypoint sh migrate -c 'DATABASE_URL=$DATABASE_MIGRATION_URL python manage.py <rotate_field_encryption|rebuild_ip_index>'`;
  - production (Phase 19) must preserve this separation in its secret management.
- 2026-11-09 — Phase 3 M1 / O1: the `migrate` service now runs **both** `migrate` and `seed_roles` as the owner role (`export DATABASE_URL="$DATABASE_MIGRATION_URL"`). `erp_app` only reads `rbac_permission`; `seed_roles`/`sync_permissions` refuse to run as `erp_app`; `create_platform_admin` (run in `api`) only checks that the catalogue is synchronized. This supersedes the 2026-11-06 note that seeding ran as `erp_app`.
- 2026-11-13 — Phase 3 M3: host-policy and connection variables documented (§5). Tenant hosts stay disabled.
