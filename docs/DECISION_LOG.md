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
| 031 | Field-level encryption for secrets at rest (`cryptography`, key ring + rotation) | **Accepted** | 2026-11-05 |
| 032 | Membership + tenant RoleAssignment implemented in Phase 3 together with RLS | **Accepted** | 2026-11-05 |
| 033 | Business roles/permissions in own `rbac` tables; reuse Django auth/session/password primitives | **Accepted (with conditions)** | 2026-11-05 |
| 034 | Email-link tokens: random, hashed, single-use, purpose-bound, expiring, invalidated, rate-limited | **Accepted** | 2026-11-05 |
| 035 | Step-up re-authentication for sensitive operations; MFA mandatory for privileged accounts only | **Accepted** | 2026-11-05 |
| 036 | Security-event IP addresses: encrypted at rest, restricted access, configurable retention + anonymization | **Accepted (owner, Q7 with privacy conditions)** | 2026-11-05 |
| 037 | Phase 2 scope decisions: phone/SMS login → Phase 14; no public registration; breach check optional/off; server-side QR; 30 min idle / 12 h absolute; new sign-in notices; Django admin disabled | **Accepted** (Q5 line amended by ADR-038) | 2026-11-05 |
| 038 | Manual MFA key entry during initial enrollment only, after re-authentication, shown once (accessibility exception to ADR-037 Q5) | **Accepted (owner, strict conditions)** | 2026-11-06 |
| 039 | `@hookform/resolvers` with its official Zod integration (Phase 2 frontend forms) | **Accepted** | 2026-11-06 |
| 040 | Phase 2 security-review hardening: account-level MFA lock, network-scoped login lock, privileged-target rule, owner-credential isolation, nonce CSP, IP side-table integrity, `__Host-` CSRF cookie, audit rollback guard | **Accepted (owner authorized the fixes)** | 2026-11-06 |
| 041 | Tenant resolution by host only; explicit platform hosts; `TENANT_HOSTS_ENABLED` gate; identical 404s; per-host sessions | Proposed (Phase 3 plan) | 2026-11-08 |
| 042 | Tenant context lifecycle: contextvar + `tenant_atomic` + query guard; one tenant transaction per request; durable audit; `TenantTask` | Proposed (Phase 3 plan) | 2026-11-08 |
| 043 | No runtime BYPASSRLS: `erp_platform` stays NOLOGIN; per-tenant iteration + minimal `SECURITY DEFINER` functions (amends ADR-009 §5) | Proposed (Phase 3 plan) | 2026-11-08 |
| 044 | Membership + scoped RoleAssignment model; composite FKs; tenant role copies; guard rails; revocation | Proposed (Phase 3 plan) | 2026-11-08 |
| 045 | Support sessions: explicit, tenant-approved by default, read-only, ≤ 2 h, audited in tenant log, revocable | Proposed (Phase 3 plan) | 2026-11-08 |
| 046 | RLS policy catalogue (standard, dual-scope, private dual-scope, registry allow-list) and CI enforcement | Proposed (Phase 3 plan) | 2026-11-08 |

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
| GitHub Actions `astral-sh/setup-uv@v6`, `pnpm/action-setup@v4` (+ checkout v5, setup-node v5, upload-artifact v4) | current majors | GitHub warns they run on the deprecated Node 20 runtime. Dependabot PRs #3, #4, #6, #7, #8 propose the next majors; review and merge them separately | Owner (Dependabot PRs) |
| Django | 5.2 LTS | ADR-003 (LTS policy); next LTS line requires a new ADR | — |

**Enforced in `.github/dependabot.yml` (2026-11-05):** `ignore` rules block updates that would break an accepted decision. Blocked: Django ≥5.3 and django-stubs ≥5.3 (ADR-003); TypeScript ≥6 and ESLint ≥10 (this ADR); `@types/node` ≥25 and the `node` image ≥25 (Node 24 LTS); the `python` image ≥3.14 (ADR-003); Redis ≥8 (this ADR); Nginx minor/major bumps, to stay on the stable line (this ADR); pgvector image majors. Lifting a block needs an ADR update first.

## ADR-031 — Field-level encryption for secrets at rest
**Status:** **Accepted** — approved by owner 2026-11-05: "Encrypt sensitive secrets at rest using maintained cryptographic libraries and secure key management. Never store plaintext MFA secrets or recovery codes."
**Owner conditions recorded:**
- **MFA secrets** are encrypted (reversible; needed to verify codes).
- **Recovery codes** are stored only as one-way hashes, never as plaintext or ciphertext.
- **Keys** come from the environment in dev and a secret manager in production; they are never committed.
- **Library:** `cryptography` (maintained), pinned per ADR-030 practice.

**Context:** MFA TOTP secrets (Phase 2), and later payment/SMS integration credentials, must not sit in plaintext in the database or in backups.

**Proposal:**
- Encrypt them with AES-GCM via `cryptography`, using a key ring from `FIELD_ENCRYPTION_KEYS`. The first key encrypts; all keys decrypt.
- A `reencrypt_fields` command handles rotation.
- Values are stored as versioned ciphertext bytes, and raw values never reach logs or APIs.
- Production keys live in a secret manager (KMS choice decided with ADR-019).

## ADR-032 — Phase boundary for tenant membership
**Status:** **Accepted** — approved by owner 2026-11-05.
- Phase 2 builds authentication and the authorization foundation.
- Tenant memberships, tenant roles and tenant-scoped records are implemented together with RLS in Phase 3.
- **Condition:** the permission interfaces must be clean enough that Phase 3 integration needs no rewrite of Phase 2. This is verified in Phase 2 plan §4.6.

**Proposal:**
- `Membership` and tenant `RoleAssignment` are tenant-owned tables, so they are built in **Phase 3** together with `TenantScopedModel`, RLS and `tenant_atomic` (ADR-009). Building them earlier would mean tenant data without RLS.
- Phase 2 delivers the scope-aware `has_perm` engine, roles, role templates and platform roles, so callers don't change when tenant sources are added.

## ADR-033 — Authorization data model
**Status:** **Accepted with conditions** — approved by owner 2026-11-05.

**Conditions:**
- Use custom business role and permission tables.
- Continue to use Django's secure password hashing, authentication primitives and session framework where appropriate.
- Do not duplicate Django security functionality unnecessarily.

The reuse list is in Phase 2 plan §6.10.

**Proposal:**
- Application authorization uses the project's `rbac` tables only: `Permission(code)`, `Role`, `RolePermission`, `PlatformRoleAssignment`, and in Phase 3 `RoleAssignment`.
- Django's `auth.Group`/`auth.Permission` (present via `PermissionsMixin`) are used only for Django admin by platform staff, and never in application permission checks.

## ADR-034 — Email-link tokens
**Status:** **Accepted** — approved by owner 2026-11-05. Password reset and email verification tokens must be cryptographically random, single-use and hashed, with expiration, invalidation and rate limiting.

**Proposal:**
- Activation, email verification, password reset and email change use random 32-byte tokens.
- Only the SHA-256 hash is stored, together with purpose, expiry, single-use `used_at` and creation IP.
- Issuing a new token invalidates older ones of the same purpose.
- Tokens travel in the URL fragment.

**Why not Django's `PasswordResetTokenGenerator`:** it can't be individually revoked, audited or purpose-scoped.

## ADR-035 — Re-authentication and mandatory MFA
**Status:** **Accepted** — approved by owner 2026-11-05.
- Sensitive operations require appropriate step-up authentication.
- MFA is required for the platform Super Admin and other **privileged accounts**, defined in Phase 2 plan §6.6.
- MFA is **not** required for every ordinary user action.

**Proposal:**
- **Sudo mode:** sensitive actions require password + MFA re-authentication within the last 10 minutes. These are password/email change, MFA disable/regenerate, platform role grants and admin MFA reset.
- **Mandatory MFA:** all platform roles from Phase 2; `tenant_owner` and `institution_admin` from Phase 3. Tenants may add more roles, but cannot remove the mandatory ones.

## ADR-036 — Security-event IP addresses
**Status:** **Accepted** — owner approval of Phase 2 Q7 "with privacy conditions", 2026-11-05. Implementation design in Phase 2 plan §6.9.

**Decision:**
- **Encrypted at rest.** IP addresses in security records (session records, audit events) are stored encrypted (ADR-031).
- **Searchable without decryption.** A keyed HMAC "blind index" allows exact-match search (e.g. "all events from this IP").
- **Restricted access.** Viewing decrypted IPs needs a separate permission, `audit.event.view_ip`, and each view is itself audited.
- **Configurable retention.** After the retention period (default 365 days), a scheduled job **anonymizes** IPs: it deletes the ciphertext and blind index and keeps only a coarse network prefix.
- **Deletion procedure.** A documented procedure erases a person's IP data on request.

**Pending legal review before production:** the retention period and lawful basis (minors' data; Bangladesh and other applicable data-protection law). This is listed in `DEVELOPMENT_PROGRESS.md` Known gaps.

## ADR-037 — Phase 2 scope decisions (owner answers to plan Q2–Q9)
**Status:** **Accepted** — owner 2026-11-05.

| Topic | Decision |
|---|---|
| Phone / SMS-code login | Moves to Phase 14 (needs an SMS provider) |
| Registration | No public registration in Phase 2; accounts are created only through authorized administrative workflows |
| Breached-password check | Disabled by default; optional, configurable integration kept |
| MFA QR code | Generated server-side; the raw MFA secret is never in API responses or logs. *Amended by ADR-038 (2026-11-06): one-time manual-key display during initial enrollment after re-authentication.* |
| Sessions | 30-minute idle timeout; 12-hour absolute lifetime |
| New sign-in notices | Sent to platform staff according to configured security policy; no sensitive data in email |
| Django admin | Disabled in production; all administration through application interfaces and audited APIs |

## ADR-038 — Manual MFA key entry (accessibility exception)
**Status:** **Accepted** — owner approval of Phase 2 plan Q10 "with strict security conditions", 2026-11-06. It **amends ADR-037** ("the raw MFA secret is never in API responses or logs") for this single, tightly controlled case. Every other part of ADR-037 is unchanged.

**Context:** users who can't scan a QR code (screen-reader users, setting up on the same phone, broken camera) need to type the key into their authenticator app.

**Decision (owner conditions):**
1. The key may be displayed **only during initial MFA enrollment**, for an unconfirmed device within its enrollment window.
2. It is shown **only after successful re-authentication**: a fresh step-up, where the login itself does not count. Step-up is allowed inside the restricted enrollment session.
3. It is shown **once**. Later requests get `410`. It is **never exposed through logs, analytics, emails, audit metadata or any later API response**.
4. If the user loses it before enrollment is completed, they **must restart MFA setup**, which generates a new secret and invalidates the pending one.
5. The MFA secret is **stored encrypted at rest** (ADR-031).

Implementation: Phase 2 plan §6.6 (manual-key subsection), §8, §10, §16 (11a).

## ADR-039 — `@hookform/resolvers`
**Status:** **Accepted** — owner approval of Phase 2 plan Q11, 2026-11-06.

**Decision:**
- Add `@hookform/resolvers` (MIT) and use its **official Zod integration** (`zodResolver` from `@hookform/resolvers/zod`) with react-hook-form.
- Pin a maintained, compatible version, recorded in `TECH_STACK.md`: 7.0.3, with peers `zod ^3.25 || ^4` and `react-hook-form ^7.55`, both compatible with the pinned zod 4.6 and react-hook-form 7.91.
- **Why:** it avoids an in-house adapter (duplicated, less tested code).

## ADR-040 — Phase 2 security-review hardening
**Status:** **Accepted** — the owner authorized every fix of the independent review of PR #15 (2026-11-06), including L5 (recovery codes for step-up). It refines ADR-033, ADR-035, ADR-036 and ADR-011 without superseding them.

**Decisions:**
1. **MFA failures are counted per account** (login MFA and step-up together): 10 failures in 15 minutes lock MFA verification for 15 minutes. A password login cannot reset the counter. Locks are audited (`identity.mfa.locked`) and notified at most once per user per day. Recovery: wait, or an administrator's MFA reset (which clears the lock).
2. **Login lockout is network-scoped:** the hard lock applies to one (email, IPv4 /24 or IPv6 /48) pair. Per email, from any network, only a progressive delay applies, capped at 30 seconds. Lock notices: at most one per user per day.
3. **Privileged-target rule:** an actor may reset MFA, deactivate/reactivate or sign out another account only if the actor holds the permission **and** every permission the target holds; only a Super Admin may act on a Super Admin. Enforced in services (`rbac.services.assert_can_act_on`).
4. **Owner-credential isolation:** runtime processes (API, worker, beat, web) never receive database owner or superuser credentials. Compose uses per-service environment allow-lists (no `env_file`); Django refuses to start a runtime process holding them; CI checks the compose configuration and the running containers. Only `migrate` (`ERP_PROCESS_ROLE=migrate`) holds the owner URL; owner-only maintenance (key rotation, IP index rebuild) runs from that container.
5. **Audit immutability boundary:** the runtime role can only SELECT/INSERT audit events; a trigger rejects UPDATE/DELETE/TRUNCATE for every role, **but the table owner can still disable the trigger with DDL**. Protection therefore rests on owner-credential isolation (4). Tamper-evident off-site audit storage (hash chain or log shipping) is planned for Phase 18.
6. **IP side table:** for the runtime role, IP rows can only be added together with their event (same transaction) and existing evidence can only be cleared (set to NULL), never rewritten; DELETE stays allowed for ADR-036 erasure.
7. **Content-Security-Policy:** per-request nonce; `script-src 'self' 'nonce-…' 'strict-dynamic'` with no `unsafe-inline`/`unsafe-eval` in production; `style-src 'self' 'unsafe-inline'` (CSS only: Radix UI injects scroll-lock styles without a nonce); `img-src 'self' data:` for the MFA QR; `frame-ancestors 'none'`. zod runs jitless so it never needs eval. API responses: `default-src 'none'`.
8. **CSRF cookie:** `__Host-csrftoken` in production (Secure, Path=/, no Domain); plain `csrftoken` only for local HTTP development. Cookies never get a `Domain` attribute, including when Phase 3 adds tenant subdomains.
9. **Audit migration rollback** is refused unless `ERP_ALLOW_AUDIT_ROLLBACK=true` in a non-production environment.
10. **Email-link tokens** are all invalidated after password change/reset, email change, MFA reset and deactivation.
11. **Step-up may use a single-use recovery code** (L5) instead of the TOTP code; the password is still required.

## ADR-041 — Tenant resolution by host; platform host separation; enablement gate
**Status:** Proposed (Phase 3 plan, `plans/PHASE_03_PLAN.md` §8; owner questions Q1, Q2, Q9). Not to be built on until accepted.

**Context:** Phase 2 maps every allowed host to the platform scope (`ScopeTargetMiddleware`), and the dev `ALLOWED_HOSTS` wildcard `.localhost` means any `*.localhost` host is served as the platform today. ADR-040 I2 requires that no tenant host is enabled before secure host-to-tenant resolution exists and is tested.

**Proposal:**
1. The tenant is derived **only** from the request host. Headers (`X-Tenant`), bodies and query strings never select the tenant.
2. `PLATFORM_HOSTS` is an explicit list (Super Admin console, "My institutions"). Platform hosts have no tenant context, so every tenant table is invisible (fail closed).
3. Tenant hosts are `{slug}.<TENANT_BASE_DOMAIN>` (dev `{slug}.localhost`); verified custom domains come later (ADR-027). Hosts are normalised (lower case, port stripped, IP literals and non-ASCII rejected) and resolved through the `SECURITY DEFINER` function `tenancy_resolve_host` (ADR-043).
4. Unknown, `provisioning` and `deleted` tenants get the **same** `404` body and timing (no tenant enumeration).
5. **Enablement gate:** `TENANT_HOSTS_ENABLED` defaults to `false` everywhere; production settings refuse `true` without `TENANT_BASE_DOMAIN`. The owner enables it in production only after the Phase 3 security review.
6. Each host has its own session: host-only cookies, `__Host-` prefix in production, never a `Domain` attribute (ADR-011, ADR-040 L6). Phase 3 uses a separate sign-in per tenant host; cross-host single sign-on needs a later ADR.

**Alternatives considered:** one shared host with the tenant in the URL path (weaker cookie isolation, no white-label domains); a tenant header (client-chosen, rejected by CLAUDE.md §10).

## ADR-042 — Tenant context lifecycle
**Status:** Proposed (Phase 3 plan §6; Q7). Refines ADR-009 §4 without changing it.

**Proposal:**
1. `apps.core.tenancy` provides a `contextvars`-based `TenantContext`, `current_tenant()`/`require_tenant()`, and `tenant_atomic(tenant)`: it opens `transaction.atomic()`, runs `set_config('app.tenant_id', …, true)` as the first statement, and restores the previous state in `finally`. Nesting with the same tenant uses a savepoint; nesting with a different tenant raises `TenantContextConflict`.
2. A `connection.execute_wrapper` guard raises `TenantContextNotApplied` for any query issued while a tenant context is active but the current transaction has not applied it (autocommit, new connection or thread, `on_commit` callback).
3. **One tenant transaction per tenant-host request.** Error responses inside it roll back. Security events that must survive a rollback are written through a second connection alias (`audit_durable`, same `erp_app` role, `CONN_MAX_AGE = 0`).
4. Side effects (email, Celery) are dispatched with `transaction.on_commit`.
5. Celery: the `TenantTask` base takes `tenant_id` explicitly, re-establishes the context with `tenant_atomic` and always resets it. Tasks without a tenant must be declared `platform_task`; a CI test enforces the declaration.
6. Cache keys: `t:{tenant_id}:…`, with a per-tenant random permission-cache version. Storage keys: `tenants/{tenant_id}/…`.
7. Only transaction-scoped database state is used, so the design remains compatible with PgBouncer transaction pooling. A PgBouncer stack test is a Phase 19 item.

**Trade-off:** request-wide transactions hold locks longer, so tenant views stay short and heavy work runs in Celery.

## ADR-043 — No runtime BYPASSRLS; cross-tenant access patterns
**Status:** Proposed (Phase 3 plan §5.2; Q3). **Amends ADR-009 §5** (the use of `erp_platform`) if accepted.

**Proposal:**
1. `erp_platform` stays `NOLOGIN`, and no runtime container holds `BYPASSRLS` credentials (consistent with ADR-040 H3 owner-credential isolation).
2. Platform needs that span tenants are met by three narrow patterns:
   - per-tenant iteration over the tenant registry, each tenant's work inside its own `tenant_atomic`;
   - a few `SECURITY DEFINER` read functions owned by `erp_owner`, with a pinned `search_path`, `EXECUTE` granted only to `erp_app`, and only the minimum columns returned (`tenancy_resolve_host`, `tenancy_memberships_of`, `tenancy_support_sessions_of`);
   - aggregates computed from registry tables only.
3. `platform_scope(reason)` becomes an audited context manager that provides these patterns. It never disables RLS.
4. Every new `SECURITY DEFINER` function needs owner review and is covered by a CI check (pinned `search_path`, no `PUBLIC` execute).

**Trade-off:** platform-wide reports are slower (iteration) than a `BYPASSRLS` query, in exchange for no credential that can read all tenants at once.

## ADR-044 — Membership and scoped role-assignment model
**Status:** Proposed (Phase 3 plan §4, §7; Q5, Q8, Q12). Implements ADR-032 within the ADR-033 data model.

**Proposal:**
1. There is one `Membership` per (tenant, user), with statuses `invited`/`active`/`suspended`/`left`. One account may belong to many tenants. Membership is never required to exist; platform users have none.
2. `RoleAssignment` (`rbac_roleassignment`, RLS) links a membership to a role at `tenant`, `institution` or `campus` scope, with `valid_from`/`valid_until`. Institution membership is **derived** from assignments, not stored.
3. **Composite foreign keys** (`(tenant_id, …)`, added via reviewed `RunSQL`) make it impossible in the database to reference another tenant's membership, role, institution or campus, or a campus outside the assignment's institution.
4. Tenant role templates are copied into each tenant as `kind = tenant` roles with `template_id`. System copies stay synced and read-only; tenants customise by cloning.
5. Two new permission sources: `TenantMembershipSource` (assignments whose scope covers the target; never sideways) and `SupportSessionSource` (ADR-045). The Phase 2 engine API is unchanged.
6. Guard rails:
   - no granting beyond one's own permissions or scope;
   - the last active `tenant_owner` cannot be removed;
   - `assert_can_act_on` is extended to members;
   - platform roles grant nothing on tenant hosts.
7. Revocation: membership, tenant and support-session status is checked uncached on every tenant request; permission caches use per-tenant versions; removing a member revokes their sessions on that tenant's hosts.
8. Default limits before billing: `max_institutions = 1`, `max_campuses = 3`, with an audited Super Admin override (ADR-010). Limits are enforced under row locks.

## ADR-045 — Support sessions
**Status:** Proposed (Phase 3 plan §9; Q4). Implements CLAUDE.md §9 and ADR-037's "no implicit tenant-data access".

**Proposal:**
1. Platform staff reach tenant data **only** through a `SupportSession`. Requesting one requires:
   - a reason (≥ 10 characters) and a ticket reference;
   - a duration of 15–120 minutes;
   - MFA and step-up re-authentication.
2. Tenant approval is required by default (a tenant setting may waive it). Sessions cannot be extended, only requested again.
3. Phase 3 sessions are **read-only**: unsafe HTTP methods are rejected, and only allow-listed `support_readable` view permissions are granted. Write access needs a new ADR.
4. Every support request is audited in the **tenant's** log (`actor_type = support`, session id). Request and end are also audited in the platform log. Tenants see a persistent banner and the session history, and can revoke at any time.
5. Support requests run as `erp_app` inside the tenant transaction. There is no `BYPASSRLS` (ADR-043).

## ADR-046 — RLS policy catalogue and enforcement
**Status:** Proposed (Phase 3 plan §5; Q10). Extends ADR-009 §3 and §6.

**Proposal:**
1. **Standard tenant tables:** `ENABLE` + `FORCE`; `USING`/`WITH CHECK` `tenant_id = ctx`. No context means no rows.
2. **Dual-scope tables** (`rbac_role`, `rbac_rolepermission`), which hold platform templates and tenant copies:
   - read `tenant_id IS NULL OR tenant_id = ctx`;
   - write `tenant_id IS NOT DISTINCT FROM ctx`.
3. **Private dual-scope tables** (`audit_auditevent`, `audit_auditeventip`): read and insert `tenant_id IS NOT DISTINCT FROM ctx`. Platform events are invisible on tenant hosts, and tenant events are invisible on the platform host. `audit_auditeventip` gains a trigger-filled `tenant_id`. Existing grants and immutability triggers are unchanged.
4. **Platform registry tables without RLS** (`tenancy_tenant`, `identity_*`, `rbac_permission`, `rbac_platformroleassignment`) hold no tenant business data. They sit on an explicit allow-list in the CI check.
5. Reversible migration operations `EnableTenantRLS` and `EnableDualScopeRLS` exist. Reversing an isolation migration is refused in production and staging (same guard as ADR-040 I1).
6. CI fails when:
   - a `tenant_id` table lacks forced RLS or a policy;
   - a dual-scope table is off the allow-list or mis-shaped;
   - a tenant model does not inherit `TenantScopedModel`;
   - a `SECURITY DEFINER` function is unsafe;
   - the code contains session-level `SET app.tenant_id` or `set_config(..., false)`.

### Change notes
- 2026-11-05 — Initial log created (Phase 0).
- 2026-11-05 — Owner approved ADR-009, ADR-010, ADR-012, ADR-013, ADR-014 (Accepted) and ADR-011 (Accepted with modification: Django session auth for browser app). Added ADR-028 (Proposed) for future mobile/third-party auth. No other ADR status changed.
- 2026-11-05 — Phase 1: ADR-015 and ADR-021 Accepted (owner approval). Added ADR-029 (Proposed, safe default: SeaweedFS for dev S3) and ADR-030 (Accepted: Phase 1 pins + recorded constraints). No other ADR changed.
- 2026-11-05 — Owner approved ADR-029 (conditional; all four conditions verified, evidence recorded) and ADR-030 (TypeScript 5.9/ESLint 9 held temporarily; upgrade tracking table added). No other ADR changed.
- 2026-11-05 — ADR-030: Dependabot `ignore` rules added to enforce accepted version policies; actions-upgrade tracking row updated with the Dependabot PRs.
- 2026-11-05 — Added ADR-031 to ADR-035 (Proposed) with the Phase 2 plan. No existing ADR changed.

- 2026-11-05 — Owner approved ADR-031, ADR-032, ADR-034 and ADR-035, and ADR-033 with conditions. Added ADR-036 (IP privacy, Q7) and ADR-037 (Q2–Q9 scope decisions) as Accepted. No other ADR changed.
- 2026-11-06 — Added ADR-038 (manual MFA key, Q10 strict conditions; amends ADR-037 Q5 line) and ADR-039 (`@hookform/resolvers`, Q11), both Accepted. ADR-037 index row annotated. No other ADR changed.
- 2026-11-06 — Phase 2 implemented (PR #15) within ADR-031 to ADR-039. No ADR added or changed; implementation deviations from the plan text are recorded in `plans/PHASE_02_PLAN.md` §18.
- 2026-11-06 — Added ADR-040 (Accepted): security-review hardening of Phase 2. No other ADR status changed; ADR-036's scope now explicitly includes IP-derived device fingerprints (90-day maximum).
- 2026-11-08 — Added ADR-041 to ADR-046 (Proposed) with the Phase 3 plan (`plans/PHASE_03_PLAN.md`). ADR-043 would amend ADR-009 §5 if accepted. No existing ADR status changed.
