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
| 009 | Tenancy model: shared schema + `tenant_id` + RLS | Proposed | 2026-11-05 |
| 010 | Tenant hierarchy Tenant → Institution → Campus | Proposed | 2026-11-05 |
| 011 | Web auth: JWT in HttpOnly cookies via Next.js BFF | Proposed | 2026-11-05 |
| 012 | UUID (v7) primary keys | Proposed | 2026-11-05 |
| 013 | Package managers: `uv` (Python), `pnpm` (JS) | Proposed | 2026-11-05 |
| 014 | Repository directory layout | Proposed | 2026-11-05 |
| 015 | REST + OpenAPI (drf-spectacular) + generated TS client | Proposed | 2026-11-05 |
| 016 | Declarative rules (JSONLogic-style), no tenant code execution | Proposed | 2026-11-05 |
| 017 | Payment gateway abstraction; initial gateways | Proposed | 2026-11-05 |
| 018 | PostgreSQL full-text search first | Proposed | 2026-11-05 |
| 019 | Hosting provider & data region | Open (needs owner input) | 2026-11-05 |
| 020 | AI provider abstraction; default provider | Proposed | 2026-11-05 |
| 021 | Initial languages: en, bn; ar (RTL) ready | Proposed | 2026-11-05 |
| 022 | Real-time: polling/SSE first; no WebSockets initially | Proposed | 2026-11-05 |
| 023 | Accounting depth: full double-entry GL | Proposed | 2026-11-05 |
| 024 | Pricing model: active-student tiers + add-ons + usage | Proposed (numbers open) | 2026-11-05 |
| 025 | Fees always post to the ledger; `accounting` entitlement gates GL features | Proposed | 2026-11-05 |
| 026 | Generic academic unit tree with configurable structure levels | Proposed | 2026-11-05 |
| 027 | TLS for tenant custom domains | Open | 2026-11-05 |

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
**Status:** Proposed. **Options:** (A) shared schema + `tenant_id` + RLS; (B) schema-per-tenant; (C) database-per-tenant. **Recommendation:** A as default; C available later for enterprise via DB routing with the same code. **Why:** single migration path, scales to thousands of tenants, lower cost, simpler analytics/pgvector; RLS gives defense-in-depth against missing filters. **Trade-offs:** relies on disciplined base classes + RLS; per-tenant restore requires logical export tooling. Details: `MULTI_TENANT_ARCHITECTURE.md` §2.

## ADR-010 — Tenant hierarchy
**Status:** Proposed. `Tenant → Institution → Campus`; a tenant (customer/contract) may own multiple institutions of different types; billing per tenant. **Alternative:** tenant = institution (simpler, but cannot model education groups under one contract). **Recommendation:** accept the three-level hierarchy.

## ADR-011 — Web authentication
**Status:** Proposed. **Recommendation:** SimpleJWT short-lived access + rotating refresh tokens stored in HttpOnly/Secure/SameSite cookies, issued through Next.js BFF route handlers; bearer tokens for future mobile apps. **Alternative:** Django session cookies (simplest, server-side revocation built in) with Next.js on same parent domain. **Trade-off:** sessions are simpler and revocable; JWT eases mobile/API clients. Both are acceptable; owner/architect to confirm before Phase 2. *Either option keeps tokens out of JS-readable storage.*

## ADR-012 — Primary keys
**Status:** Proposed. **Recommendation:** UUIDv7 generated in Python (PostgreSQL 17 has no native `uuidv7()`; Python 3.13 stdlib lacks `uuid7`) via a small vetted dependency, stored as native `uuid`. **Why:** non-enumerable IDs across tenants, good index locality. **Alternative:** UUIDv4 (no dependency, worse locality) or bigint + public UUID (more complexity).

## ADR-013 — Package managers
**Status:** Proposed. `uv` for Python (fast, lockfile), `pnpm` for JS (efficient, strict). Alternatives: pip-tools/Poetry; npm.

## ADR-014 — Directory layout
**Status:** Proposed. `backend/` (Django, apps under `backend/apps/<module>`), `frontend/` (Next.js), `packages/api-client/`, `infra/`, `docs/`, `.github/`. See `CLAUDE.md` §16.

## ADR-015 — API style
**Status:** Proposed. REST under `/api/v1`, OpenAPI via drf-spectacular, generated TS types/client (`openapi-typescript`). GraphQL rejected for now (complexity, authorization surface).

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
**Status:** Proposed. English + Bengali at launch; RTL-ready layout for Arabic (and Urdu later). Bengali digit display optional per tenant.

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

### Change notes
- 2026-11-05 — Initial log created (Phase 0).
