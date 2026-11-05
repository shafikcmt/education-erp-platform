# Decision Log (Architecture Decision Records)

> Status values: `Proposed` (awaiting owner approval — do not build on it unless marked *safe default*), `Accepted`, `Superseded`, `Rejected`.
> Never delete or rewrite entries; supersede them with a new ADR. Update `CLAUDE.md` when an accepted decision changes it.

| ADR | Title | Status | Date |
|---|---|---|---|
| 001 | Monorepo | Accepted (owner mandate) | 2026-11-05 |
| 002 | Modular monolith first | Accepted (owner mandate) | 2026-11-05 |
| 003 | Core technology stack | Accepted (owner mandate) | 2026-11-05 |
| 004 | PostgreSQL only; no MongoDB without justification | Accepted (owner mandate) | 2026-11-05 |
| 005 | Single codebase, configuration-driven customization, versioned extensions | Accepted (owner mandate) | 2026-11-05 |
| 006 | Strict server-side tenant isolation | Accepted (owner mandate) | 2026-11-05 |
| 007 | Financial operations in DB transactions | Accepted (owner mandate) | 2026-11-05 |
| 008 | AI and custom modules never bypass authorization | Accepted (owner mandate) | 2026-11-05 |
| 009 | Tenancy model: shared schema + `tenant_id` + RLS, transaction-scoped tenant context | **Accepted** | 2026-11-05 |
| 010 | Tenant hierarchy Tenant → Institution → Campus; tenant-level subscription; configurable campus limits | **Accepted** | 2026-11-05 |
| 011 | Web auth: Django session auth (HttpOnly/Secure/SameSite cookies + CSRF); separate token path for mobile/third-party | **Accepted (with owner modification)** | 2026-11-05 |
| 012 | UUIDv7 primary keys via pinned library behind `core.ids` abstraction | **Accepted** | 2026-11-05 |
| 013 | Package managers: `uv` (Python), `pnpm` (JS) | **Accepted** | 2026-11-05 |
| 014 | Repository directory layout (`backend/`, `frontend/`, `packages/api-client/`, `infra/`; `docs/` + `CLAUDE.md` at root) | **Accepted** | 2026-11-05 |
| 015 | REST + OpenAPI (drf-spectacular) + generated TS client | **Accepted** | 2026-11-05 |
| 016 | Declarative rules (JSONLogic-style), no tenant code execution | Proposed | 2026-11-05 |
| 017 | Payment gateway abstraction; initial gateways | Proposed | 2026-11-05 |
| 018 | PostgreSQL full-text search first | Proposed | 2026-11-05 |
| 019 | Hosting provider & data region | Open (needs owner input) | 2026-11-05 |
| 020 | AI provider abstraction; default provider | Proposed | 2026-11-05 |
| 021 | Initial languages: en, bn; ar (RTL) ready | **Accepted** | 2026-11-05 |
| 022 | Real-time: polling/SSE first; no WebSockets initially | Proposed | 2026-11-05 |
| 023 | Accounting depth: full double-entry GL | Proposed | 2026-11-05 |
| 024 | Pricing model: active-student tiers + add-ons + usage | Proposed (numbers open) | 2026-11-05 |
| 025 | Fees always post to the ledger; `accounting` entitlement gates GL features | Proposed | 2026-11-05 |
| 026 | Generic academic unit tree with configurable structure levels | Proposed | 2026-11-05 |
| 027 | TLS for tenant custom domains | Open | 2026-11-05 |
| 028 | Mobile / third-party API authentication mechanism (library & token format) | Proposed | 2026-11-05 |
| 029 | Dev/self-hosted object storage: SeaweedFS (S3 API) instead of MinIO; production storage configurable | **Accepted** (owner, conditional — conditions verified) | 2026-11-05 |
| 030 | Phase 1 toolchain, library and image pins; TypeScript 5.9 + ESLint 9 held temporarily | **Accepted** (owner; upgrades tracked) | 2026-11-05 |

---

## ADR-001 — Monorepo
**Status:** Accepted (owner mandate). **Context:** backend, frontend, generated client, infra and docs must evolve together. **Decision:** single GitHub repository `education-erp-platform`. **Consequences:** one PR can change API + client + UI atomically; CI must path-filter jobs to stay fast.

## ADR-002 — Modular monolith first
**Status:** Accepted (owner mandate). **Decision:** one Django backend composed of bounded modules with enforced dependency rules; one Next.js app. **Consequences:** simple deploys and transactions; service extraction only by new ADR with measured need.

## ADR-003 — Core technology stack
**Status:** Accepted (owner mandate). Next.js 16, TypeScript, Tailwind CSS, shadcn/ui; Python 3.13, Django 5.2 LTS, DRF; PostgreSQL 17 + JSONB + pgvector; Redis, Celery, Docker, Docker Compose, Nginx; S3-compatible/MinIO; GitHub Actions; Sentry + structured logging. Details: `TECH_STACK.md`.

## ADR-004 — PostgreSQL only
**Status:** Accepted (owner mandate). **Decision:** PostgreSQL is the sole primary datastore; JSONB for flexible data; pgvector for embeddings. MongoDB or other primary DBs require a new ADR with technical justification. Redis is cache/broker only (never source of truth).

## ADR-005 — Single codebase, configuration-driven
**Status:** Accepted (owner mandate). No per-institution codebases/forks/branches; L1/L2/L3 customization (`CUSTOMIZATION_ENGINE.md`); versioned configuration and extensions.

## ADR-006 — Strict server-side tenant isolation
**Status:** Accepted (owner mandate). Tenant resolved and enforced server-side; fail closed; isolation tests mandatory per module.

## ADR-007 — Financial operations in DB transactions
**Status:** Accepted (owner mandate). All money operations atomic; plus (as part of this ADR's implementation guidance) Decimal money, row locking, idempotency keys, immutable postings.

## ADR-008 — AI/custom modules never bypass authorization
**Status:** Accepted (owner mandate). AI tools and custom modules run the full authorization pipeline as the requesting user.

## ADR-009 — Tenancy model
**Status:** **Accepted** — approved by owner 2026-11-05.
**Original proposal (retained for history):** Options were (A) shared schema + `tenant_id` + RLS; (B) schema-per-tenant; (C) database-per-tenant. Recommended A as default, with C available later for enterprise via DB routing using the same code. Reasons: one migration path, scales to thousands of tenants, lower cost, simpler analytics/pgvector, RLS as defense-in-depth. Trade-offs: depends on disciplined base classes + RLS; per-tenant restore needs logical export tooling.

**Decision:**
1. **One shared PostgreSQL database and schema.** Every tenant-owned table has `tenant_id UUID NOT NULL` (FK → `tenancy_tenant`, indexed, normally the leading column of composite indexes), and its model inherits `TenantScopedModel`.
2. **Application-layer enforcement (primary).** `TenantManager` filters by the current tenant context and **raises** if no context is set. Saves reject a `tenant_id` that differs from the context. Platform-wide access is possible only through the explicit, audited `platform_scope(reason=...)`.
3. **Row-Level Security (defense-in-depth).** Every tenant table gets `ENABLE ROW LEVEL SECURITY` **and** `FORCE ROW LEVEL SECURITY`, plus one policy:
   `USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (same expression)`.
   If the setting is missing or empty the expression evaluates to NULL, so **no rows are visible or writable (fail closed)**.
4. **Transaction-scoped tenant context.** The tenant is set with `SELECT set_config('app.tenant_id', <uuid>, true)` (`is_local = true`, equivalent to `SET LOCAL`) as the first statement of **every** transaction that touches tenant data, and is discarded automatically at COMMIT/ROLLBACK. Session-level `SET` is forbidden because it would leak across pooled connections. Concretely:
   - One helper, `core.db.tenant_atomic(tenant)`, opens `transaction.atomic()` and sets the value. It is the only sanctioned way to open a tenant transaction.
   - Tenant-scoped API requests run inside `tenant_atomic` (via middleware/view wrapper). Celery tenant tasks use the same helper through the tenant-aware base task. Management commands that touch tenant data must use it too.
   - A guard installed with `connection.execute_wrapper` detects a query issued while a tenant context is active but `app.tenant_id` has not been set in the current transaction, and raises `TenantContextNotApplied`. Detailed mechanics are finalized in the Phase 3 plan.
   - Compatible with PgBouncer **transaction** pooling. Session pooling is not required.
5. **Database roles.**
   - `erp_owner` owns the schema and runs migrations.
   - `erp_app` is the runtime role: not a superuser, not the table owner, `NOBYPASSRLS`, with only the DML grants it needs. Audit tables are INSERT/SELECT only.
   - `erp_platform` is a restricted `BYPASSRLS` role used only by `platform_scope()` code paths.
   - Superusers and `BYPASSRLS` roles skip RLS, so **tests and the app must connect as `erp_app`**; otherwise RLS tests prove nothing.
6. **Automated cross-tenant isolation tests (mandatory, CI-blocking).** Every module provides the suite in `MULTI_TENANT_ARCHITECTURE.md` §8. On top of that, a platform-level CI check fails if any table that has a `tenant_id` column lacks RLS enabled + forced + a policy, or if any concrete model with tenant data does not inherit `TenantScopedModel`.
7. **Database-per-tenant (option C)** remains a future enterprise option. It needs a new ADR and uses the same code.

**Consequences:** All later phases build on these primitives (delivered in Phase 3; DB roles are provisioned from Phase 1). Raw SQL must run inside `tenant_atomic` or `platform_scope`.

## ADR-010 — Tenant hierarchy
**Status:** **Accepted** — approved by owner 2026-11-05.
**Decision:**
- Hierarchy is `Platform → Tenant → Institution → Campus`.
- A tenant (customer/contract) can own **multiple institutions**, which may be of different institution types. Each institution has **one or more campuses**; exactly one campus per institution is flagged `is_main`.
- **Subscription ownership is at tenant level:** one active subscription per tenant; entitlements and usage are metered per tenant.
- **Campus and institution limits are configurable.** Plans carry `limits.max_institutions` and `limits.max_campuses` (data, not code). Super Admin can override them per tenant (audited). They are enforced server-side in the tenancy service at create time; exceeding a limit returns `403 limit_exceeded`. Downgrades never delete existing campuses; creating new ones is blocked until the tenant is within the limit.
- Configuration can be overridden at tenant, institution and campus scope (resolution order in `CUSTOMIZATION_ENGINE.md` §2).

**Alternative rejected:** tenant = institution. It is simpler, but it cannot model education groups under one contract.

## ADR-011 — Web authentication
**Status:** **Accepted with owner modification** — approved 2026-11-05.
**Original proposal (not adopted for the browser app):** SimpleJWT access + rotating refresh tokens in HttpOnly cookies, issued through Next.js BFF route handlers.

**Decision:**
1. **First-party browser app uses Django-managed session authentication** (`django.contrib.sessions` + DRF `SessionAuthentication`).
2. **Cookies:**
   - Session cookie: `HttpOnly`, `Secure` (all non-local environments), `SameSite=Lax`, **host-only** (no `Domain` attribute), so a session on one tenant's subdomain or custom domain is never sent to another tenant's host. Cookie name configurable (`__Host-` prefix in production when compatible).
   - CSRF cookie: `Secure`, `SameSite=Lax`. It stays JS-readable so the frontend can send `X-CSRFToken`; it is an anti-forgery token, not a credential.
3. **CSRF protection** is enforced on all unsafe methods, including login/logout. `CSRF_TRUSTED_ORIGINS` is limited to platform domains and verified tenant domains.
4. **Same-origin topology:** Nginx serves the Next.js app and the Django API on the same host (`/` → web, `/api/` → api), so cookies are first-party and browser CORS is not needed for the web app.
   - Next.js server components call the API over the internal network, forwarding the incoming `Cookie` header and preserving `Host`/`X-Forwarded-Host` for tenant resolution.
   - **Next.js never holds, mints or stores credentials.** There are no BFF token-exchange handlers.
5. **Session hygiene:**
   - Session key rotated on login and on privilege change (`cycle_key`).
   - All sessions invalidated on password change/reset.
   - Idle timeout and absolute lifetime are configurable per tenant within platform bounds.
   - Sessions stored with the `cached_db` backend (Redis cache + PostgreSQL), so they can be listed and revoked by user.
   - MFA is a second step before the session becomes fully authenticated.
6. **No access or refresh tokens in `localStorage`, `sessionStorage`, IndexedDB or JS-readable cookies — ever.**
7. **Future mobile apps and third-party APIs** get a **separate** authentication path. It must be designed now so it can be added without changing authorization:
   - Authentication classes are pluggable; the authorization pipeline (`CLAUDE.md` §10) is identical for every authentication method.
   - Endpoints are separated, e.g. `/api/v1/oauth/…` or `/api/v1/auth/token/…`.
   - Requirements: OAuth 2.1-compatible flows (Authorization Code + PKCE for mobile/third-party, client credentials for server integrations), short-lived access tokens, rotating refresh tokens with reuse detection, scoped tokens bound to tenant + permissions, revocation, and audit.
   - Library and token format (opaque vs JWT) are **not chosen yet** → **ADR-028 (Proposed)**.

**Consequences:**
- `djangorestframework-simplejwt` is **not** a Phase 1/2 dependency.
- Phase 2 delivers session login/logout/MFA/CSRF endpoints.
- The frontend sends `credentials: 'include'` + `X-CSRFToken`.

## ADR-012 — Primary keys
**Status:** **Accepted** — approved by owner 2026-11-05.
**Context:** PostgreSQL 17 has no native `uuidv7()`, and the Python 3.13 standard library has no `uuid.uuid7()` (added in 3.14).

**Decision:**
- All primary keys are **UUIDv7** values (RFC 9562), stored in PostgreSQL's native `uuid` type and generated **in the application**.
- Generation uses a **maintained, version-pinned** library compatible with Python 3.13. Candidate: `uuid-utils` via its stdlib-compatible API (`uuid_utils.compat.uuid7()`, which returns `uuid.UUID`); fallback: `uuid6`. The final choice is confirmed in Phase 1 after checking current maintenance status, then pinned in `uv.lock`.
- **Encapsulation:** all code calls `core.ids.new_id() -> uuid.UUID` (and models use `core.models.UUIDv7PrimaryKey` / `BaseModel.id = UUIDField(primary_key=True, default=new_id, editable=False)`). **No module imports the UUID library directly**; this is enforced by a lint/import-linter rule. Switching to stdlib `uuid.uuid7()` after a future Python upgrade then becomes a one-file change.
- `new_id()` must return a standard `uuid.UUID` (version 7) and be monotonic within a process. Unit tests verify version bits, ordering and type.
- UUIDv7 embeds the creation timestamp. That is acceptable: IDs are identifiers, not secrets, and are never used for authorization.

**Alternatives rejected:** UUIDv4 (poor index locality); bigint + public UUID (extra complexity).

## ADR-013 — Package managers
**Status:** **Accepted** — approved by owner 2026-11-05.

**Decision — Python (`uv`):**
- `backend/pyproject.toml` + committed `backend/uv.lock`.
- Python version pinned in `backend/.python-version` (`3.13`).
- Dependency groups for dev/test tooling.
- CI and Docker install with `uv sync --frozen` (fail if the lockfile is stale).

**Decision — JavaScript (`pnpm`):**
- A pnpm workspace at the repository root (`pnpm-workspace.yaml` with `frontend` and `packages/*`).
- Committed `pnpm-lock.yaml`.
- pnpm version pinned through the root `package.json` `packageManager` field (activated with Corepack).
- CI and Docker use `pnpm install --frozen-lockfile`.

**Not used:** pip, Poetry, pip-tools, npm or yarn for project dependencies.

## ADR-014 — Directory layout
**Status:** **Accepted** — approved by owner 2026-11-05.

**Decision:**
```
/CLAUDE.md  /README.md  /docs/                (root; documentation stays at root)
/backend/      Django project: config/, apps/<module>/, tests/, pyproject.toml, uv.lock
/frontend/     Next.js app
/packages/api-client/   generated TypeScript types/client from the OpenAPI schema
/infra/        docker/, nginx/, scripts/
/.github/      workflows/, dependabot.yml, pull_request_template.md
/docker-compose.yml  /.env.example  /Makefile  /package.json  /pnpm-workspace.yaml   (root tooling)
```
Django apps live in `backend/apps/<module_code>/` (module codes as in `CLAUDE.md` §5).

## ADR-015 — API style
**Status:** **Accepted** — approved by owner 2026-11-05 (with the Phase 1 plan). REST under `/api/v1`, OpenAPI via drf-spectacular, generated TS types/client (`openapi-typescript`). GraphQL rejected for now (complexity, authorization surface).

## ADR-016 — Rules engine
**Status:** Proposed. Declarative JSON expression AST (JSONLogic-style) evaluated by a sandboxed, allow-listed evaluator (library or small in-house evaluator — decide in Phase 5 after security review). Tenant-supplied executable code is forbidden.

## ADR-017 — Payment gateways
**Status:** Proposed (provider choice open). `PaymentGateway` abstraction. Candidates: Stripe (SaaS billing, international), SSLCommerz / bKash / Nagad (Bangladesh fee collection & local SaaS billing). Selection requires verification of merchant eligibility, fees, recurring support, settlement terms — **owner input required before Phase 10**.

## ADR-018 — Search
**Status:** Proposed. PostgreSQL FTS + `pg_trgm` first; external search engine only by new ADR with measured need.

## ADR-019 — Hosting & data region
**Status:** Open. Candidates: AWS / DigitalOcean / Hetzner / local Bangladesh data center; managed PostgreSQL with pgvector support required. Depends on budget, latency to Bangladesh, data-residency requirements, managed-service availability. **Owner input required before Phase 19** (affects backups and storage choices).

## ADR-020 — AI provider
**Status:** Proposed. Provider abstraction; default chat provider Anthropic Claude (model IDs in configuration); embedding provider TBD; tenant opt-in required. Bengali/Arabic quality to be evaluated in Phase 16.

## ADR-021 — Languages
**Status:** **Accepted** — approved by owner 2026-11-05 (with the Phase 1 plan). English + Bengali at launch; RTL-ready layout for Arabic (and Urdu later). Bengali digit display optional per tenant.

## ADR-022 — Real-time
**Status:** Proposed. Polling/SSE for job progress and notifications initially; Django Channels/WebSockets only if a feature demonstrably needs it.

## ADR-023 — Accounting depth
**Status:** Proposed. Full double-entry general ledger with immutable postings; fees/payroll/hostel/transport post automatically. Alternative: fee ledger only (faster to build, weaker finance offering).

## ADR-024 — Pricing model
**Status:** Proposed; **numbers open**. Plans `trial/starter/growth/professional/enterprise`, active-student tiers + paid add-ons + usage (SMS, storage, AI). Prices stored as data. Owner to provide/approve price points after market research.

## ADR-025 — Fees and ledger
**Status:** Proposed. The accounting posting engine is part of the platform financial core and always installed so every fee transaction posts balanced journal entries; the `accounting` module entitlement unlocks GL UI (vouchers, ledgers, statements, bank reconciliation). **Why:** guarantees financial integrity for all tenants regardless of plan.

## ADR-026 — Academic structure model
**Status:** Proposed. A generic, self-referencing `academic_unit` tree whose levels are configured per institution (`structure_level`), so School/College/University/Madrasa/Coaching/Training structures are data. Validated in Phase 6 plan.

## ADR-027 — TLS for custom domains
**Status:** Open. Options: Caddy on-demand TLS in front of Nginx, managed edge/CDN with custom hostnames, or certbot automation. Decide in Phase 18.

## ADR-028 — Mobile / third-party API authentication mechanism
**Status:** Proposed (created 2026-11-05 as a follow-up of ADR-011).

**Context:** ADR-011 requires a separate, OAuth/JWT-compatible authentication path for future mobile apps and third-party APIs, without changing the authorization pipeline.

**Options:**
- (A) `django-oauth-toolkit` — OAuth 2 provider, Authorization Code + PKCE, client credentials, opaque tokens stored in DB, revocation built in.
- (B) SimpleJWT — JWT access + rotating refresh, with blacklist for revocation.
- (C) Both: OAuth flows issuing JWT access tokens.

**Leaning:** (A), because opaque, revocable, scoped tokens fit multi-tenant revocation needs.

**Decision timing:** before the first mobile app or public API work (no earlier than Phase 17/18). Not needed for Phases 1–16.

## ADR-029 — Dev/self-hosted object storage: SeaweedFS (S3 API)
**Status:** **Accepted** — approved by owner 2026-11-05, *subject to* verified bucket isolation, S3 compatibility, backup/restore and provider portability, with production storage kept configurable. All four conditions were verified on 2026-11-05 (evidence below).
*(Originally recorded as Proposed / safe default during Phase 1 implementation.)*

**Context:**
- The approved Phase 1 plan specified MinIO images (`minio/minio`, `minio/mc`). During Phase 1 implementation (2026-11-05), neither image was available: "not found" via the Docker Hub mirror, and quay.io refused the request. This is consistent with MinIO ending distribution of community container images in late 2025.
- ADR-003 (accepted) mandates "S3-compatible storage or MinIO", so any S3-compatible server satisfies it.

**Decision:**
- Development and CI use **SeaweedFS** (`chrislusf/seaweedfs:4.50`, Apache-2.0) in single-container `weed server -s3` mode, as compose service `objectstore` with a one-shot `objectstore-init` that creates the bucket.
- The application talks only to the **standard S3 API** through `django-storages`/`boto3`, configured entirely by environment variables (`S3_ENDPOINT_URL`, `S3_BUCKET`, keys). Swapping to MinIO (self-built), Garage, Ceph RGW or managed S3 is a config change, with no code change.
- The S3 identity is least-privilege: Read/Write/List/Tagging on the app bucket only, with no admin rights. A test confirmed that creating or writing other buckets is denied.

**Production:** managed S3-compatible storage is still preferred; the decision belongs to ADR-019 (hosting). Production storage stays configurable: the provider is selected only by `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY`, with no provider-specific code.

**Verification of the approval conditions (2026-11-05):**

| Condition | How it is verified | Result |
|---|---|---|
| **Bucket isolation** | `apps/core/tests/test_s3_integration.py` (opt-in `S3_INTEGRATION=1`; runs in CI `e2e-smoke` and `make s3-check`): app identity cannot create buckets; cannot list, put, get or delete in an existing foreign bucket (`erp-isolation-probe`); anonymous object/list requests return 403; wrong secret rejected; presigned URLs reject a tampered signature (403) and expire (403) | 9/9 passed on SeaweedFS 4.50 |
| **S3 compatibility** | Same suite: django-storages round-trip with `file_overwrite=False`; put/get/head with content type + user metadata; range GET; 12 MiB multipart upload with SHA-256 match; copy; paginated listing; presigned GET | Passed on SeaweedFS 4.50 |
| **Backup / restore** | `manage.py s3_mirror --to-dir` (SHA-256 manifest), then destroy the object-store volume, recreate it empty (bucket re-created by `objectstore-init`), `s3_mirror --from-dir` | 3 objects / 6,293,612 bytes restored byte-identical (SHA-256), content types preserved |
| **Provider portability** | (1) The same compatibility suite, unmodified, against a second provider (RustFS, throwaway container, root credentials, so the two root-incompatible isolation tests are excluded). (2) `s3_mirror` migrated SeaweedFS → RustFS. (3) The app was pointed at RustFS by environment variables only, and `smoke_check` storage passed | 7/7 passed on RustFS; migrated data identical; smoke `storage: ok` |

**Operational notes:**
- Restore needs the target bucket to exist first. By design the app identity cannot create buckets, so run the provisioning step (`objectstore-init`, or the provider's console/IaC) before `s3_mirror --from-dir`.
- `s3_mirror` loads one object at a time into memory, which suits dev/CI volumes. A streaming or provider-native tool for production volumes is decided in Phase 19 together with the backup schedule and retention.

**Alternatives considered:**
- Garage (AGPL-3.0, smaller ecosystem).
- RustFS (young project).
- Building MinIO from source (maintenance burden).
- `bitnami/minio` (not reachable / deprecated catalogue).

## ADR-030 — Phase 1 toolchain, library and image pins
**Status:** **Accepted** — owner approved the Phase 1 choices on 2026-11-05.

**Decisions (approved):**
- `uuid-utils` 1.2.x is pinned in `uv.lock`, behind `apps.core.ids.new_id()`; an import-linter contract forbids direct imports elsewhere. Verified on 2026-11-05:
  - Python 3.13 cp313 wheels exist, and release 1.2.0 is dated 2026-10-26 (maintained);
  - `uuid_utils.compat.uuid7()` returns a stdlib `uuid.UUID` with version 7;
  - values are stored in PostgreSQL 17 native `uuid` and are monotonic in-process (tested).
- `django-environ` with separate `dev`, `test` and `prod` settings modules. `prod` refuses to start with a weak or missing `DJANGO_SECRET_KEY` or empty `DJANGO_ALLOWED_HOSTS` (tested).
- Minimal custom user model `identity.User` was created before the first migration: UUIDv7 PK, unique email (also a case-insensitive unique index), no username, `PermissionsMixin` for Django-admin platform staff only. No auth flows (Phase 2).
- Node.js **24.22.2** LTS, pinned in `.nvmrc`, `package.json#engines`, the Docker base `node:24.22.2-alpine` and CI (`node-version-file: .nvmrc`).
- Nginx is in the default dev stack: official `nginx:1.28.3-alpine`, run as non-root uid 101 on port 8080 with read-only rootfs (`nginxinc/nginx-unprivileged` was not reachable).
- Redis **7.4.12** (`redis:7.4.12-alpine`).
- Other images pinned: `pgvector/pgvector:0.8.7-pg17` (PostgreSQL 17.x, pgvector 0.8.7), `python:3.13.18-slim-bookworm`, `axllent/mailpit:v1.28.4`, `chrislusf/seaweedfs:4.50`.

**Owner approval 2026-11-05:** TypeScript 5.9 and ESLint 9 are kept **temporarily** because of current tooling compatibility; future upgrades are tracked (see "Upgrade tracking" below).

**Constraints discovered (recorded so they are revisited, not forgotten):**
- **TypeScript 5.9.3**, not 6.x/7.x: typescript-eslint requires `<6.1` and openapi-typescript requires `^5`.
- **ESLint 9.39.5**, although npm marks it deprecated: plugins bundled by `eslint-config-next` 16.4.5 (react, import, jsx-a11y) do not yet declare ESLint 10 support. Revisit when they do.
- **pnpm 10.34.9** (mature major already used here; pnpm 12 exists). Revisit with Dependabot.
- **Django stays on 5.2 LTS** (5.2.19), even though 6.x is released, per ADR-003.

**Deferred (to keep dependencies justified):** TanStack Query, react-hook-form and zod are not installed until a phase uses them (Phase 2 forms).

**Upgrade tracking (revisit at the start of every phase; Dependabot opens PRs weekly):**

| Item | Held at | Upgrade trigger | Owner of check |
|---|---|---|---|
| TypeScript | 5.9.3 | typescript-eslint supports TS ≥ 6.1 **and** openapi-typescript supports TS ≥ 6 | Phase kickoff review |
| ESLint | 9.39.5 | `eslint-config-next` and its bundled plugins (react, import, jsx-a11y) declare ESLint 10 | Phase kickoff review |
| pnpm | 10.34.9 | Planned major bump with lockfile regeneration in a dedicated PR | Dependabot |
| GitHub Actions `astral-sh/setup-uv@v6`, `pnpm/action-setup@v4` | current majors | GitHub warns they run on the deprecated Node 20 runtime; bump to majors targeting Node 24 when available | Dependabot (`github-actions`) |
| Django | 5.2 LTS | ADR-003 (LTS policy); next LTS line requires a new ADR | — |

### Change notes
- 2026-11-05 — Initial log created (Phase 0).
- 2026-11-05 — Owner approved ADR-009, ADR-010, ADR-012, ADR-013, ADR-014 (Accepted) and ADR-011 (Accepted with modification: Django session auth for browser app). Added ADR-028 (Proposed) for future mobile/third-party auth. No other ADR status changed.
- 2026-11-05 — Phase 1: ADR-015 and ADR-021 Accepted (owner approval). Added ADR-029 (Proposed, safe default: SeaweedFS for dev S3) and ADR-030 (Accepted: Phase 1 pins + recorded constraints). No other ADR changed.
- 2026-11-05 — Owner approved ADR-029 (conditional; all four conditions verified, evidence recorded) and ADR-030 (TypeScript 5.9/ESLint 9 held temporarily; upgrade tracking table added). No other ADR changed.
