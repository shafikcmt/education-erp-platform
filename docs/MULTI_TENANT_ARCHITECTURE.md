# Multi-Tenant Architecture

> Tenant isolation is a **non-negotiable** platform guarantee. See `CLAUDE.md` §2 and §10.

> **Status (2026-11-08):** this document describes the **target** design. Nothing tenant-scoped is implemented yet. The detailed Phase 3 design is **approved** in `plans/PHASE_03_PLAN.md` (revision 3), with ADR-041–047 Accepted. Where the plan refines this document (for example, `platform_scope()` without a `BYPASSRLS` login, ADR-043), **the plan and the ADRs take precedence**. This document will be updated to describe the implemented design as Phase 3 milestones land.

## 1. Tenancy hierarchy

```
Platform
└── Tenant            (customer organization; owns subscription, users' memberships, settings, data)
    └── Institution   (school / college / university / madrasa / coaching_center / training_institute)
        └── Campus    (branch / location; at least one "main" campus per institution)
```

- A tenant may own several institutions (e.g. an education group running a school, a college and a madrasa).
- **All tenant-owned rows carry `tenant_id`.** Institution- and campus-level rows additionally carry `institution_id` / `campus_id` where applicable.
- Billing, entitlements and usage limits are per **tenant** (one subscription per tenant; ADR-010 accepted). Configuration can be overridden per institution and campus.
- Institution and campus counts are capped by configurable plan limits `max_institutions` / `max_campuses`. Super Admin overrides are audited. Limits are enforced server-side at creation (`403 limit_exceeded`), and a downgrade never deletes existing campuses.

## 2. Tenancy model (ADR-009 — **Accepted** 2026-11-05)

**Shared database, shared schema, `tenant_id` discriminator column + PostgreSQL Row-Level Security (RLS) as defense-in-depth.**

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| A. Shared schema + `tenant_id` + RLS | Simple migrations (one schema), scales to thousands of tenants, cross-tenant platform analytics possible, pgvector/FTS simple, cheapest | Isolation relies on discipline + RLS; noisy-neighbor risk | **Recommended** |
| B. Schema-per-tenant (e.g. django-tenants) | Stronger logical separation, per-tenant restore easier | Migrations run N times (slow with thousands of tenants), connection/search_path complexity, catalog bloat, harder cross-tenant analytics | Not recommended as default |
| C. Database-per-tenant | Strongest isolation, per-tenant backup/residency | Highest cost and operational overhead | Offered **only** to enterprise tenants later, same code, via DB routing |

Option C remains available for enterprise/data-residency needs without code forks, because all access already goes through tenant-aware routing.

## 3. Tenant resolution

1. **Host-based:** `{tenant_slug}.<platform-domain>` or a verified custom domain (`TenantDomain` table, DNS TXT verification).
2. **Authenticated membership:** the user must hold an active `Membership` in the resolved tenant (except public endpoints such as the tenant's online admission form, which resolve tenant by host and expose only explicitly public resources).
3. **Platform console:** `admin.<platform-domain>` — platform staff only, no implicit tenant; tenant access via explicit support session.
4. API clients (future mobile apps) send `X-Tenant` header **in addition** to a token; the server verifies the token's membership for that tenant. The header alone grants nothing.

The resolved tenant is stored in a request-scoped context (`contextvars`) — `core.tenant_context.current_tenant()`.

## 4. Enforcement layers

| Layer | Mechanism |
|---|---|
| 1. Middleware | `TenantMiddleware` resolves tenant, verifies membership, sets context; rejects mismatches (403) |
| 2. ORM | `TenantScopedModel` base with default manager `TenantManager` that automatically filters by `current_tenant()` and **raises `TenantContextMissing`** if no tenant is set. `save()` sets/validates `tenant_id` and refuses to write a row whose `tenant_id` differs from context. |
| 3. Database (RLS) | For every tenant table: `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` + policy `USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (same)`. Unset context → NULL → no rows (fail closed). The app connects as `erp_app` (non-superuser, non-owner, `NOBYPASSRLS`); migrations run as `erp_owner`. |
| 4. Services | Service functions take `tenant` (and `actor`) explicitly; cross-entity references validated to belong to same tenant (e.g. invoice's student must be same tenant). |
| 5. Serializers | Related-object fields use tenant-scoped querysets (no IDs from other tenants accepted). |
| 6. Celery | Tasks take `tenant_id` argument; a base task class sets tenant context + RLS setting before running; tasks without tenant must be declared platform tasks. |
| 7. Cache | Keys namespaced `t:{tenant_id}:...`. |
| 8. Files | Object keys `tenants/{tenant_id}/...`; downloads via short-lived presigned URLs after permission check. |
| 9. Search/AI | Every FTS query and pgvector similarity query filtered by `tenant_id` (and RLS). |
| 10. Logs | `tenant_id` included in structured logs; logs never contain other tenants' data in shared error messages. |

**Platform scope:** platform code that legitimately needs cross-tenant access (billing runs, metering, migrations, Super Admin aggregates) uses an explicit `with platform_scope(reason=...)` context, which connects with a role permitted to bypass RLS (`BYPASSRLS` limited role) and writes an audit entry. Use is restricted by code review and lint rule.

### 4.1 Transaction-scoped tenant context (ADR-009, ADR-042) — implemented in Phase 3 M1

**Implemented (M1, `backend/apps/core/tenancy/`):**

| Primitive | Behaviour |
|---|---|
| `TenantContext`, `current_tenant()`, `require_tenant()`, `bind_tenant()` | The tenant lives in a `ContextVar` (local to each thread and asyncio task). Tenant ids must be canonical UUIDv7 (`InvalidTenantId` otherwise). Binding a different tenant raises `TenantContextConflict`. A bound context alone grants nothing in the database |
| `tenant_atomic(tenant=None, using="default")` (also `apps.core.db.tenant_atomic`, the ADR-009 name) | <ul><li>The single sanctioned way to open a tenant transaction.</li><li>Its first statement is `SELECT pg_catalog.set_config('app.tenant_id', <uuid>, true)`.</li><li>Nesting with the same tenant uses a savepoint; a different tenant raises `TenantContextConflict`.</li><li>When opened inside an enclosing transaction it did not start, it clears the setting before releasing its savepoint.</li><li>Context and connection state are always restored in `finally`.</li></ul> |
| Query guard | <ul><li>A `connection.execute_wrapper` installed on every connection (`connection_created`).</li><li>While a tenant is bound, a query runs only if *that connection's* current transaction applied *that* tenant; otherwise it raises `TenantContextNotApplied` before reaching PostgreSQL. This covers autocommit, `on_commit` callbacks, new threads and other aliases.</li><li>Leftover connection state without a context raises `TenantContextLeak`.</li></ul> |
| `TenantScopedModel` / `TenantManager` | <ul><li>The default and base manager filter by the bound tenant and raise `TenantContextMissing` without one.</li><li>`save`, `update`, `bulk_create` and `bulk_update` refuse to create rows in, or move rows to, another tenant (`TenantMismatch`).</li><li>M1 uses a plain indexed `tenant_id` UUID column; M2 turns it into a foreign key to the tenant registry.</li></ul> |
| `app_tenant_id()` (SQL, migration `core.0003`) | <ul><li>Reads the transaction-local setting and returns NULL when it is missing or malformed, so every policy fails closed.</li><li>`STABLE`, `SECURITY INVOKER`.</li><li>`EXECUTE` only for the owner and `erp_app`.</li></ul> |
| `EnableTenantRLS`, `EnableDualScopeRLS(private=…)` (`core.db_operations`) | <ul><li>ENABLE + FORCE RLS with per-command policies named `tenant_isolation_{select,insert,update,delete}`.</li><li>Reversal is refused in production and staging, and elsewhere unless `ERP_ALLOW_ISOLATION_ROLLBACK=true`.</li></ul> |
| `platform_scope(operation, actor, reason)` | <ul><li>Accepts only catalogued operations P1–P16; P3, P11, P15 and P16 are disabled.</li><li>Re-checks the actor's permission without cache and audits start and end.</li><li>Refuses to run inside a tenant context, and refuses nesting.</li><li>Allows `tenant_atomic` only for operations catalogued with the targeted or per-tenant mechanism.</li><li>Never sets a tenant, changes role or uses `BYPASSRLS` (ADR-043). `erp_platform` stays `NOLOGIN` and unused.</li></ul> |
| Boundary leak detectors | Request start/finish and Celery task prerun/postrun clear and report any leftover tenant state. They raise in tests (`TENANCY_LEAK_STRICT`) and log errors in production |

**Rules:**
- **Forbidden:** session-level `SET app.tenant_id`, `set_config(..., false)`, `SET ROLE`, `RESET ROLE` and `SET SESSION`. A static check in `tests/isolation` enforces this.
- **Pooling:** only transaction-scoped state is used, so the design is compatible with PgBouncer transaction pooling.
- **Tests:** RLS tests connect as `erp_app`. Superusers and `BYPASSRLS` roles skip RLS, so tests run with them would prove nothing.
- **Not yet implemented (later milestones):**
  - request middleware and host resolution (M3);
  - the durable audit connection and `lock_timeout` (M3);
  - `TenantTask` (M7);
  - the tenancy models (M2).

## 5. Unique constraints and identifiers

- Business identifiers are unique **per tenant** (e.g. `UNIQUE (tenant_id, student_code)`), never globally.
- Primary keys are UUIDs (ADR-012) so IDs are not enumerable across tenants.
- Composite foreign key patterns (`(tenant_id, id)`) may be used on critical relations to make cross-tenant references impossible at DB level (decided in Phase 3 per table).

## 6. Tenant lifecycle

| State | Meaning | Allowed |
|---|---|---|
| `provisioning` | Being created / preset applied | Platform only |
| `trial` | Trial plan active | Full use within trial limits |
| `active` | Paid subscription | Full use |
| `past_due` | Payment overdue (grace period) | Full use + banners |
| `suspended` | Grace expired or manual suspension | Read-only or login-blocked (configurable); data retained |
| `offboarding` | Cancellation requested | Export available |
| `deleted` | Data purged after retention window | Nothing (tombstone record only) |

Provisioning steps: create tenant → create first institution with type preset → create main campus → assign plan (trial) → create owner membership + role → seed preset config/roles → send invitation.

## 7. Support access

- Platform support cannot read tenant data by default.
- A **support session** requires a reason, a ticket reference, a duration (max 2 h) and an access level (read-only by default). Tenant-admin approval is required when the tenant's setting says so.
- **Activation:** starting a session requires platform-staff MFA and step-up (ADR-035).
- **Execution:** during the session, requests run **inside the tenant context** (`tenant_atomic`, normal RLS as `erp_app`; **not** the `BYPASSRLS` role). Permissions come only from a fixed read-only `SupportSessionSource` (Phase 2 plan §4.5).
- **Audit and control:** every request is audited with `actor_type = support` and `support_session_id`. Tenant admins can view the history and revoke an active session, and sessions expire automatically.
- **Built in Phase 3**; designed in the Phase 2 plan.

## 7a. Dual-scope tables (Phase 2 plan §4.6)

`rbac_role`, `rbac_rolepermission` and `audit_auditevent` hold platform rows (`tenant_id IS NULL`) and, from Phase 3, tenant rows. With `ctx = NULLIF(current_setting('app.tenant_id', true), '')::uuid`, their Phase 3 RLS policies are:

- **Writes:** `WITH CHECK (tenant_id IS NOT DISTINCT FROM ctx)` — no tenant context means only platform rows can be written; a tenant context means only that tenant's rows.
- **Reads, `rbac_*`:** `USING (tenant_id IS NULL OR tenant_id = ctx)`, so tenants can see the system templates.
- **Reads, `audit_auditevent`:** `USING (tenant_id IS NOT DISTINCT FROM ctx)`, so tenants and the platform never see each other's events.

These tables are the **only** exception to "unset context → no rows", because their platform rows contain no tenant data. They are kept on an explicit allowlist in the CI RLS check, and a tenant context still never sees another tenant's rows.

## 8. Mandatory isolation tests (every module)

For every tenant-owned resource:
1. User of tenant A listing the resource never sees tenant B rows.
2. User of tenant A fetching/updating/deleting tenant B object by ID gets 404 (not 403, to avoid existence disclosure).
3. Creating an object referencing a tenant B foreign key is rejected.
4. ORM access without tenant context raises.
5. Celery task for tenant A cannot touch tenant B data.
6. RLS policy test: raw SQL with `app.tenant_id` = A returns zero tenant B rows.

A shared pytest fixture/helper set (`tests/isolation/`) is built in Phase 3 and reused by every later module.

**Platform-level CI checks (ADR-009, ADR-046). Implemented in M1 in `backend/tests/isolation/`:**

- **`test_rls_coverage.py`** classifies every table in `public` against `registry.py`. The classes are:
  - standard tenant table;
  - dual-scope;
  - self-scoped registry;
  - scheduled for RLS in a later milestone, which must have no RLS until then;
  - allow-listed registry table, which needs a justification and named access-control tests that must exist.

  It fails when:
  - a table lacks ENABLE or FORCE;
  - a table's policies differ from the reference shape of its class (taken from probe tables built by the real migration operations);
  - a table is unregistered;
  - a tenant-to-tenant foreign key lacks `tenant_id`;
  - a unique constraint doesn't start with `tenant_id`;
  - a `SECURITY DEFINER` function or owner-only policy is unsafe or unapproved;
  - a tenant model doesn't inherit `TenantScopedModel`.

  Meta-tests on a throwaway schema prove that each check detects a real violation.
- **`test_db_role_restrictions.py`:**
  - only `erp_platform` has `BYPASSRLS` (apart from the cluster bootstrap superuser, which the application never uses);
  - `erp_platform` cannot log in and has no members;
  - the application roles inherit no privileged role;
  - the runtime connection is `erp_app`.
- **`test_static_checks.py`:** forbidden role and session statements are absent from runtime code, migrations and infrastructure scripts.
- **`test_concurrency.py`:**
  - K1: 20 threads × 50 operations alternating tenants;
  - K2: one reused connection across tenants and the platform.

A failure blocks merge.

### Change notes
- 2026-11-05 — Initial version (Phase 0).
- 2026-11-05 — Updated for owner-approved ADR-009/010/011/012/013/014 (session auth, transaction-scoped RLS context, DB roles, UUIDv7 abstraction, tenant-level subscription with campus limits, uv/pnpm, layout).
- 2026-11-05 — Aligned with Phase 2 approvals (ADR-031 to ADR-037); see `plans/PHASE_02_PLAN.md` rev. 2.
- 2026-11-06 — Phase 3 prerequisite (security review I2): `apps.rbac.middleware.ScopeTargetMiddleware` currently treats **every** host as the platform host. It must be replaced by host-based tenant resolution **before** any tenant host is added to `ALLOWED_HOSTS`; session and CSRF cookies stay host-only (no `Domain`) for tenant subdomains (ADR-040).
- 2026-11-08 — Added a status note pointing to the proposed Phase 3 plan (ADR-041–046). No design change.
- 2026-11-08 — Status note updated for plan rev. 2 (ADR-041–047). No design change.
- 2026-11-08 — Status note updated for plan rev. 3. No design change.
- 2026-11-08 — Status note: Phase 3 plan approved; ADR-041–047 Accepted. No design text changed yet.
- 2026-11-08 — Phase 3 M1: §4.1 and §8 now describe the implemented tenant context primitives, RLS tooling and CI checks; items for later milestones are labelled.
