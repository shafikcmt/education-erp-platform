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

### 3.1 Implemented data model (Phase 3 M2)

- **Tables:** `tenancy_tenant` (registry, self-scoped RLS), `tenancy_tenantdomain`, `tenancy_institution`, `tenancy_campus`, `tenancy_membership`, `tenancy_invitation` and `tenancy_supportsession`. The six tenant tables have standard RLS and composite `(tenant_id, …)` foreign keys.
- **Host resolution:** `tenancy_resolve_host()` (F1) exists, called only through `apps.tenancy.selectors.platform` inside `platform_scope(P1)`. **No request path uses it yet.** Middleware and tenant hosts arrive in M3, and tenant hosts stay disabled until the production domain and the security review are approved (D1).
- **Further reading:** plan §4, §5, §7 and §24.4.

### 3.2 Implemented request path (Phase 3 M3)

Tenant hosts are **disabled by default in every environment** (`TENANT_HOSTS_ENABLED=false`) and stay disabled in production until the domain and the security review are approved (D1). The text of §3 items 1–3 describes the target; item 4 (`X-Tenant`) is future work and no header ever selects a tenant today.

```
RequestID → Security → HostPolicy → Session → Common → CSRF → Auth → SessionSecurity
  → TenantResolution → TenantTransaction → ApiNoStore → XFrameOptions
```

| Step | Where | Behaviour |
|---|---|---|
| Health probes | `HostPolicyMiddleware` | `/healthz`, `/readyz`: host-independent, no session, no tenant |
| Platform host | `HostPolicyMiddleware` | Exact match in `PLATFORM_HOSTS` (lower-case, port stripped). Autocommit, as in Phase 2 |
| Disabled mode | `HostPolicyMiddleware` | Every other host gets the uniform `404 not_found`. No session, no query |
| Tenant candidate | `HostPolicyMiddleware` | Exactly `<slug>.<TENANT_BASE_DOMAIN>` with a valid, non-reserved slug; anything else gets the same 404 |
| Resolution | `TenantResolutionMiddleware` | One F1 lookup (`platform_scope("P1")`, never cached). Unknown, unverified, provisioning and deleted tenants get the same 404. Sets `request.tenant` and `request.scope_target` |
| Session binding | `TenantResolutionMiddleware` | A session presented on another host than the one it was created on is ignored (anonymous request, cookie dropped on that host, stored session untouched) and reported as `tenancy.isolation.blocked` |
| Transaction | `TenantTransactionMiddleware` | One `tenant_atomic` per tenant request with `lock_timeout = 5s`; status ≥ 400 rolls back; streaming bodies are refused; `tx_ms` is logged, with a warning above 2 s |
| Host class | `TenantTransactionMiddleware.process_view` | Views are platform-only unless they declare `host_classes`; the wrong host gets the uniform 404 |
| Gate | `apps.tenancy.access` | Signed-in requests need an active membership and a usable tenant: `tenant_suspended`, `not_a_member`, `membership_inactive`, `tenant_unavailable` (writes during offboarding) |

- **Sign-in on a tenant host** returns the generic `invalid_credentials` error for every refusal (D7).
- **Authorization:** no tenant RBAC source exists before M4, so nobody holds a tenant permission on a tenant host; platform roles never apply there. Only self-service permissions (own account) work.
- **Database connections:** `CONN_MAX_AGE = 0` on every alias; production refuses anything else (D4).
- **Durable audit:** denial and failure events written inside a tenant context use the `audit_durable` connection and survive the rollback (see `SECURITY.md` §6).
- **Further reading:** `plans/PHASE_03_M3_PLAN.md` §11, plan §24.6, ADR-048.

### 3.3 Implemented tenant authorization (Phase 3 M4)

- **Role assignments** (`rbac_roleassignment`, tenant-owned, RLS): a member holds a tenant role in a scope (`tenant`, `institution` or `campus`). Composite `(tenant_id, …)` keys make a reference to another tenant's member, role, institution or campus, to a template role, or to a campus of another institution impossible in the database.
- **Tenant roles:** every tenant has a read-only system copy of each role template, kept in line by `manage.py sync_tenant_roles` (P7). Tenants customise by cloning; clones are never synced.
- **Evaluation:** `TenantMembershipSource` unions the assignments in force whose scope covers the target (tenant ⊇ institution ⊇ campus, never sideways). It grants nothing outside that tenant's transaction, for an inactive membership, or for a tenant that is not `active` (owners only while `offboarding`). Platform roles never grant anything in a tenant.
- **Guard rails:** permission in the scope of the change; no granting or revoking above one's own permissions; no acting on a more privileged member; the last active owner cannot be demoted, suspended or removed.
- **Revocation:** effective on the next request (uncached membership check, per-tenant cache version); suspension and removal end the member's sessions on that tenant's hosts.
- **Not yet:** HTTP endpoints (M8). Details: plan §24.7.

### 3.4 Implemented support access (Phase 3 M5)

- Platform staff reach tenant data **only** through a support session of that tenant: requested with a reason, a ticket and 15–120 minutes (P6), approved by a tenant owner unless the owner turned approval off (D5), and usable only on that tenant's host, with the staff member's own account and MFA.
- Access is **read-only** and limited to the `support_readable` view codes; writes are refused before the view runs. Every support request is audited in the tenant's log in the same transaction as its data; no audit row, no data (R9).
- Sessions end on revocation, on the staff member's request, at the end of their window, or when the tenant is suspended; each ends the staff member's sign-ins on that tenant's hosts.
- **Suspended tenants (D2):** no support access at all; only owners sign in, into a restricted mode limited to reviewing support access.
- Owners are emailed on request, start and approval-setting changes; members see active sessions (banner data). Details: plan §24.8.

### 3.5 Implemented dual-scope tables (Phase 3 M6)

| Table | Class | Effect |
|---|---|---|
| `rbac_role`, `rbac_rolepermission` | dual | Platform roles and templates are readable in every context; a tenant's own roles only inside that tenant. Writes only in the current scope |
| `audit_auditevent`, `audit_auditeventip` | private dual | The platform log is visible only without a tenant context; each tenant's log only inside that tenant. Nobody writes into another scope's log |

- Jobs that must reach every row of these tables (IP retention P10, data-subject erasure, key rotation, index rebuild) run once for the platform and once per tenant; RLS is never bypassed.
- Every table is now covered: none is pending RLS (`tests/isolation/registry.py`). Details: plan §24.9.

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
- 2026-11-09 — §3.1: implemented tenancy data model (Phase 3 M2). No design change.
- 2026-11-13 — Phase 3 M3: §3.2 added (implemented request path: host policy, resolution, tenant transaction, gate). The 2026-11-06 prerequisite about `ScopeTargetMiddleware` is met: it is removed and replaced by host-based resolution; tenant hosts remain disabled.
- 2026-11-16 — Phase 3 M4: §3.3 added (implemented tenant authorization).
- 2026-11-18 — Phase 3 M5: §3.4 added (implemented support access).
- 2026-11-18 — Phase 3 M6: §3.5 added (dual-scope RLS on roles and the audit log).
