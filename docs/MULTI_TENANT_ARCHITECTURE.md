# Multi-Tenant Architecture

> Tenant isolation is a **non-negotiable** platform guarantee. See `CLAUDE.md` §2 and §10.

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

### 4.1 Transaction-scoped tenant context (ADR-009, accepted)

- **Single entry point:** `core.db.tenant_atomic(tenant)` opens `transaction.atomic()` and immediately runs `SELECT set_config('app.tenant_id', %s, true)`. The value lives only until COMMIT/ROLLBACK.
- **Forbidden:** session-level `SET app.tenant_id`, or `set_config(..., false)`. Either would leak tenant context across pooled connections.
- **Where it is used:**
  - Tenant-scoped API requests: wrapped by middleware or a view wrapper.
  - Celery tenant tasks: through the tenant-aware base task.
  - Management commands and data migrations that touch tenant data.
  - Nested `atomic()` blocks (savepoints) inherit the transaction's setting.
- **Guard:** a `connection.execute_wrapper` raises `TenantContextNotApplied` if SQL runs while a tenant context is active but `app.tenant_id` was not applied in the current transaction. Exact mechanics are specified in the Phase 3 plan.
- **Platform scope:** `platform_scope(reason)` uses the separate `erp_platform` role (`BYPASSRLS`) and writes an audit event.
- **Pooling:** compatible with PgBouncer transaction pooling.
- **Tests:** RLS tests connect as `erp_app`. Superusers and `BYPASSRLS` roles skip RLS, so tests run with them would prove nothing.

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
- A **support session** requires: reason, ticket reference, duration (max e.g. 2 h), optional tenant-admin approval (tenant setting), and is fully audited (every request logged with `support_session_id`). Tenant admins can view support-access history.

## 8. Mandatory isolation tests (every module)

For every tenant-owned resource:
1. User of tenant A listing the resource never sees tenant B rows.
2. User of tenant A fetching/updating/deleting tenant B object by ID gets 404 (not 403, to avoid existence disclosure).
3. Creating an object referencing a tenant B foreign key is rejected.
4. ORM access without tenant context raises.
5. Celery task for tenant A cannot touch tenant B data.
6. RLS policy test: raw SQL with `app.tenant_id` = A returns zero tenant B rows.

A shared pytest fixture/helper set (`tests/isolation/`) is built in Phase 3 and reused by every later module.

Platform-level CI checks (ADR-009):
- (a) every table with a `tenant_id` column has RLS enabled + forced + a policy;
- (b) every concrete model holding tenant data inherits `TenantScopedModel`;
- (c) the test database user is `erp_app`, not a superuser.

A failure blocks merge.

### Change notes
- 2026-11-05 — Initial version (Phase 0).
- 2026-11-05 — Updated for owner-approved ADR-009/010/011/012/013/014 (session auth, transaction-scoped RLS context, DB roles, UUIDv7 abstraction, tenant-level subscription with campus limits, uv/pnpm, layout).
