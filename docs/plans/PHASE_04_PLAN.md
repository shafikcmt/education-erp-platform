# Phase 4 Plan — Module Registry and Feature Entitlement Engine

- **Status:** **Approved** (owner, 2026-11-21: "approved and continue develop same"). Phase 3 approved the same day. ADR-050 to ADR-054 Accepted.
- **Depends on:** Phase 3 (Complete; owner approval pending). Accepted ADRs: ADR-009/043 (tenancy and platform operations), ADR-010 (limits), ADR-035 (MFA), ADR-046 (RLS catalogue).
- **Roadmap scope (`DEVELOPMENT_ROADMAP.md` Phase 4):**
  - `module_registry`: manifests, dependency validation, tenant module resolution and cache, feature flags;
  - `billing` foundations: plans, prices, add-ons, subscriptions, usage records, trials, Super Admin plan management, limit enforcement;
  - the `ModuleEntitled` permission class;
  - entitlements in `/me/context/`;
  - entitlement-driven navigation;
  - the URL audit for module declarations.
- **Not in scope:** payment gateways (ADR-017, Proposed), real prices (ADR-024: numbers are owner data, never code), SaaS invoices and dunning (Phase 10/19), usage sources that don't exist yet (students, SMS, storage, AI).

## 1. Goals

1. Every module is described by a **manifest** (code, version, category, dependencies, sellable flag, permissions). Manifests are synced into a platform registry the same way permissions are (owner-run bootstrap).
2. A tenant's **entitlements** are derived from data:
   - platform modules ∪ plan modules ∪ active add-ons ∪ active overrides;
   - then the dependency closure;
   - stored as a per-tenant snapshot and cached with a tenant version.
3. **Server-side enforcement on every path:**
   - `ModuleEntitled("<code>")` on tenant views;
   - `require_module()` in services and tenant tasks;
   - `403 module_not_entitled`.

   The UI only hides what the server refuses.
4. **Plans and limits are data:**
   - `max_institutions` / `max_campuses` come from the plan, with the existing audited per-tenant override on top (ADR-010);
   - no price numbers are seeded.
5. **Feature flags** (rollout control) stay separate from entitlements (commercial).
6. **Isolation** like Phase 3:
   - every new table gets its RLS class;
   - every platform path is a catalogued operation;
   - cross-tenant tests.

## 2. Data model (proposed)

| Table | Owner | RLS class (ADR-046) | Notes |
|---|---|---|---|
| `module_registry_module` | platform | registry allow-list (no tenant data) | code (PK, `snake_case`), name/name_i18n, category (`platform`/`standard`/`extension`), version, sellable, dependencies (codes), deprecated_at |
| `module_registry_featureflag` | platform | registry allow-list | key, description, default_enabled, rules JSONB (percentage, plan codes, tenant allow-list); no code branches per tenant |
| `billing_plan` | platform | registry allow-list | code (`trial`/`starter`/`growth`/`professional`/`enterprise` + custom), name, is_public, limits JSONB (`max_institutions`, `max_campuses`, later others) |
| `billing_planmodule` | platform | registry allow-list | plan ↔ module |
| `billing_addon` | platform | registry allow-list | code, module (or usage pack), name |
| `billing_price` | platform | registry allow-list | plan/add-on, currency (ISO-4217), interval, amount `NUMERIC(18,2)`. **Rows entered by the owner; none seeded** |
| `billing_subscription` | platform (one per tenant) | **self-scoped** like `tenancy_tenant`: a tenant sees only its own row; writes only through platform operations | tenant_id (unique), plan, status (`trialing`/`active`/`past_due`/`suspended`/`canceled`/`expired`), trial_ends_at, current_period_end, limit overrides stay on the tenant registry |
| `billing_subscriptionitem` | platform | self-scoped (via subscription) | add-ons with quantity and validity |
| `module_registry_tenantmodule` | tenant | **standard tenant RLS** | resolved snapshot: module, source (`platform`/`plan`/`addon`/`override`/`trial`), enabled, valid_from/until |
| `module_registry_override` | platform | self-scoped | Super Admin grant or revoke per tenant and module, with reason, expiry and audit |
| `billing_usagerecord` | tenant | standard tenant RLS | metric, value, period. Phase 4 records `institutions` and `campuses` only |

Composite `(tenant_id, …)` keys for tenant-to-tenant references, as in Phase 3. All migrations are additive.

## 3. Entitlement resolution

```
entitled(tenant) = closure( platform_modules
                          ∪ plan.modules
                          ∪ active add-ons
                          ∪ active overrides(grant) ) − active overrides(revoke)
```

- **Dependency closure:** a module is enabled only if all its dependencies are enabled. A broken dependency disables the dependent module and is reported (never silently enabled).
- **Recompute:** synchronously inside the transaction of every change (plan assignment, add-on, override, expiry sweep). The snapshot rows are written in that tenant's transaction (mechanism T). The tenant cache version is bumped, as RBAC already does.
- **Expiry:** trials and timed overrides are expired by a platform task that fans out tenant tasks (as the Phase 3 support-session sweep does).
- **Suspended subscription:** tenant status follows it only by an explicit P5 action. Phase 4 does not suspend tenants automatically (no billing events exist yet).

## 4. Enforcement

- `ModuleEntitled(code)`, a DRF permission class evaluated **before** the permission check. Platform modules (`core`, `tenancy`, `identity`, `rbac`, `audit`, …) are always entitled.
- `require_module(code)` for services, tenant tasks and (Phase 16) AI tools.
- **URL audit extension:** every tenant-host view declares `module_code`. The test fails for an undeclared view or an unknown code. Platform views are exempt.
- **Downgrade:** data is never deleted. A non-entitled module answers `403 module_not_entitled`. Read-only grace is a per-module policy (question Q3).

## 5. Platform operations (catalogue additions)

| # | Operation | Permission | Mechanism |
|---|---|---|---|
| P17 | Manage modules, plans, add-ons, prices, feature flags | `billing.plan.manage`, `module_registry.flag.manage` (MFA, step-up for prices) | R |
| P18 | Assign plan, add-ons, trial, overrides for a tenant | `billing.subscription.manage` (MFA + step-up + reason) | R + T (snapshot and tenant audit) |
| P19 | Entitlement and trial expiry sweep | system | I |
| P20 | Registry sync of module manifests | operator (`seed_roles` step) | R |

`platform_billing` gets P17/P18 read and manage codes; `super_admin` holds all; `platform_support` gets read-only views.

## 6. API (proposed)

- **Platform:** `/platform/modules/` (read); `/platform/plans/`, `/platform/addons/`, `/platform/prices/` (CRUD); `/platform/feature-flags/`; `/platform/tenants/{id}/subscription/` (read, assign plan, add-ons, trial, overrides).
- **Tenant:** `/me/context/` gains `entitlements` (modules, limits with current usage, flags), and `/tenant/subscription/` (read-only, `billing.subscription.view`).
- OpenAPI with 0 warnings; generated TypeScript client.

## 7. Frontend

- Navigation and dashboard cards gated by **entitlements and permissions** (`/me/context/`).
- Platform: plans and add-ons (prices entered by the owner), tenant subscription panel (plan, add-ons, trial, overrides with reason and step-up).
- Tenant: "Subscription" page (plan, modules, limits and usage). English and Bengali.

## 8. Tests and gates

- Entitlement resolution (closure, overrides, expiry); plan changes update entitlements on the next request; cache invalidation.
- Non-entitled calls refused on every tenant view: the URL audit plus a parametrised test.
- RLS coverage and cross-tenant tests for every new tenant table. Self-scoped subscription tests (raw SQL as `erp_app`).
- Concurrency: two subscription changes for the same tenant serialise (row lock); limits respect plan and override.
- Phase 3 suites, E2E and the 8 CI jobs stay green. Coverage gates are unchanged.

## 9. Milestones

| M | Deliverable |
|---|---|
| M1 | Module manifests, registry tables, sync command, CI catalogue check |
| M2 | Billing data model (plans, add-ons, prices, subscriptions, items, overrides) with RLS classes and catalogue P17–P20 |
| M3 | Entitlement resolution, snapshot, cache, expiry sweep; limits from the plan with the tenant override |
| M4 | `ModuleEntitled`, `require_module`, URL audit `module_code`, `module_not_entitled` |
| M5 | Platform and tenant APIs, OpenAPI and client |
| M6 | Frontend (platform plan management, tenant subscription page, entitlement-driven navigation), en + bn |
| M7 | E2E, docs, security self-review, Phase 4 PR |

## 10. Proposed ADRs

- **ADR-050:** module manifest format and owner-run registry sync (like permissions).
- **ADR-051:** billing tables are platform registry tables. The tenant reads only its own subscription (self-scoped RLS). All writes go through catalogued platform operations P17–P20.
- **ADR-052:** entitlement resolution with a dependency closure, a stored tenant snapshot and a versioned cache. `403 module_not_entitled`.
- **ADR-053:** feature flags are data-driven rollout controls (default, percentage, plan, tenant allow-list), separate from entitlements.

ADR-017 (gateways) and ADR-024 (pricing numbers) stay **Proposed** and are not built on.

## 11. Questions for the owner

1. **Self-service sign-up (Q6 from Phase 3):** in Phase 4 (with trial plans and abuse controls) or in Phase 5? Recommendation: Phase 5. Phase 4 keeps provisioning Super Admin only.
2. **Trial:** length is data. Should a new tenant start on `trial` automatically at provisioning? Recommendation: yes; the Super Admin can change it.
3. **Downgrade behaviour** for a module that is no longer entitled: hidden (403) or read-only for a grace period? Recommendation: 403, with export remaining possible later.
4. **Who manages plans:** `platform_billing` with MFA + step-up, or Super Admin only? Recommendation: `platform_billing` and Super Admin.
5. **Limit types:** confirm institutions and campuses stay **hard** limits; student tiers (later) **soft**. Recommendation: as in `SUBSCRIPTION_AND_BILLING.md` §3.

## 12. Owner decisions (2026-11-21, ADR-054)

The owner approved the plan with the recommended answers:

| # | Decision |
|---|---|
| Q1 | Self-service sign-up is **Phase 5**. Phase 4 keeps provisioning Super Admin only |
| Q2 | New tenants start on the `trial` plan at provisioning; a Super Admin can change it |
| Q3 | A module that is no longer entitled answers `403 module_not_entitled` (no read-only grace); data is kept |
| Q4 | Plans, add-ons, prices and flags are managed by `platform_billing` and Super Admin, with MFA (step-up for prices and subscription changes) |
| Q5 | Institution and campus limits stay **hard**; student tiers (later) will be **soft** |

## 13. Implementation notes (appended during implementation)

### 13.1 M1 — module manifests and registry (2026-11-21, branch `feat/phase-04-m1`)

| # | Note |
|---|---|
| P1 | New app `apps.module_registry` with `Module` (`module_registry_module`): a global catalogue, **SELECT-only** for `erp_app` (migration 0002), on the registry allow-list with access tests |
| P2 | Each installed app declares `MODULE` in its `manifest.py` (core, identity, rbac, audit, tenancy, module_registry). The code must equal the app label |
| P3 | Modules not built yet live in `apps/module_registry/catalog.py` with dependencies from `MODULE_CATALOG.md` §1. They are synced with `available = False`, so they can be packaged but never entitled until their code ships. `fees` depends on `students` only, because the ledger posting engine is always installed (ADR-025, Proposed, not built on) |
| P4 | Validation fails the sync and CI: canonical code format, known categories, `MAJOR.MINOR.PATCH`, known dependencies, no cycles, platform modules never sellable and never depending on sellable ones |
| P5 | `sync_modules` is owner-only and audited (`module_registry.catalog.synced`). It runs in the compose `migrate` step after `seed_roles` and in the test bootstrap. `catalog_drift()` is the read-only check. Permission added: `module_registry.module.view` (47 codes) |

### 13.2 M2 — billing data model, overrides, flags (2026-11-21, branch `feat/phase-04-m2`)

| # | Note |
|---|---|
| P6 | New app `apps.billing`: `Plan`, `PlanModule`, `AddOn` and `Price` are platform registry tables (allow-list, with access tests). `Subscription` (one per tenant) and `SubscriptionItem` are per-tenant registry rows. `FeatureFlag` and `ModuleOverride` live in `module_registry` |
| P7 | `EnableSelfScopedRLS` takes `key` (`id` or `tenant_id`) and `tenant_writes`. Subscriptions, items and overrides use `key="tenant_id", tenant_writes=False`: a tenant context reads only its own rows and can never write, and the platform (no context) writes. `tenancy_tenant` is unchanged. Self-scoped registry models are exempt from the `TenantScopedModel` check because the platform reads them without a context |
| P8 | Catalogue additions: **P17** (catalogue management: `billing.plan.manage`, `billing.price.manage` (step-up), `module_registry.flag.manage`), **P18** (tenant subscription and overrides: `billing.subscription.manage`, step-up, reason 10–200 characters, both logs), **P19** (expiry sweep, system, I; used from M3), **P20** (catalogue sync: disabled as a runtime scope, because it is the owner bootstrap) |
| P9 | **Prices are never seeded or edited:** adding a price deactivates the previous active one for the same target, currency and interval. Amounts are `NUMERIC(18,2)` with an ISO-4217 check and are never negative. No plan rows are created by code (the `trial` plan is owner data; M3 assigns it at provisioning only if it exists) |
| P10 | Permissions: `billing.plan.view|manage`, `billing.price.manage`, `billing.subscription.view_any|manage`, `billing.subscription.view` (tenant, support-readable) and `module_registry.flag.manage`, 54 codes in total. `platform_billing` holds the billing and flag codes (ADR-054 Q4); `tenant_owner` gets `billing.subscription.view`. The H2 rule now protects `platform_billing` holders from `platform_support` (the authorization test fixture uses an empty role) |
| P11 | Feature flags are evaluated from data only (ADR-053): tenant list, then plan list, then a stable percentage bucket of `sha256(key:tenant)`, then the default |

### 13.3 M3 — entitlement resolution, snapshot, expiry sweep, plan limits (2026-11-21, branch `feat/phase-04-m3`)

| # | Note |
|---|---|
| P12 | `module_registry_tenantmodule` (standard tenant RLS) stores the resolved snapshot: module, source (`platform`/`plan`/`addon`/`override`), enabled, `disabled_reason` (`not_built`, `missing_dependency`, `revoked`). `entitlements.resolve()` computes it; `recompute()` rewrites it only inside the tenant's own transaction (mechanism T) and bumps the tenant cache version |
| P13 | Plan modules count while the subscription is `trialing` (trial not ended), `active` or `past_due`; `suspended`, `canceled` and `expired` keep only platform modules (ADR-054 Q3). A broken dependency disables the dependent module and never enables the dependency. Unbuilt modules (`available = False`) are never enabled, including unbuilt platform modules (`files`, `notifications_core`) |
| P14 | `enabled_modules()` reads the snapshot through a cache keyed by the tenant version (TTL 300 s); `require_module()` raises `403 module_not_entitled` (`ModuleNotEntitledError`). Every P18 change and override recomputes synchronously, so the next request sees it |
| P15 | **P19 sweep** `module_registry.sweep_entitlements` (hourly beat, audited platform scope): ends lapsed trials (`expired`), add-on items and overrides, then fans out `module_registry.recompute_entitlements` per affected tenant |
| P16 | Limits: defaults → the plan's `limits` (hook `TENANCY_PLAN_LIMITS`, so tenancy does not import billing) → the audited ADR-010 override, which always wins. Without a plan and an override, the Phase 3 behaviour is unchanged. Limits stay hard (ADR-054 Q5) |
| P17 | Trial at provisioning (ADR-054 Q2): hook `TENANCY_PROVISIONING_HOOKS` starts the `trial` plan inside the P4 scope **only if the owner created a `trial` plan with `trial_days`** (new nullable `Plan.trial_days`, 1–365). No plan rows are created by code; a hook failure is logged and the tenant keeps platform modules |

### 13.4 M4 — enforcement (2026-11-21, branch `feat/phase-04-m4`)

| # | Note |
|---|---|
| P18 | `ModuleEntitled("<code>")` (`apps/module_registry/permissions.py`) is a DRF permission class evaluated before the permission check: on a tenant request for a module the tenant lacks it raises `403 module_not_entitled`. Platform modules pass without a lookup; platform-host requests and anonymous callers are left to the view's other classes (anonymous callers get `401` and learn nothing about entitlements). Unknown codes fail at declaration |
| P19 | `ModuleGatedView` prepends the class from the view's required `module_code`. `TenantView` uses it (`tenancy` by default; role and assignment views `rbac`, audit views `audit`); identity views reachable on tenant hosts declare `identity` |
| P20 | **URL audit:** every view reachable on a tenant host must declare an installed `module_code`; a non-platform module must be enforced with `ModuleEntitled`. Platform-only views are exempt |
| P21 | Denials are audited as `authz.denied` (`module`, `reason: module_not_entitled`), aggregated per actor and module per minute, written durably on tenant hosts so they survive the rolled-back request |
| P22 | `tenant_task(module=…)`: a tenant task of a module is refused (`TenantTaskRefused`) for tenants not entitled to it; `require_module()` (M3) remains the service-layer guard |
| P23 | Every Phase 3 tenant view belongs to a platform module, so no behaviour changes today; the probe view `/_probe/module/` (tests only, module `academics`) exercises the full path. OpenAPI is unchanged (the mixin has no docstring so operation descriptions stay as they were) |

### 13.5 M5 — APIs, OpenAPI and client (2026-11-21, branch `feat/phase-04-m5`)

| # | Note |
|---|---|
| P24 | Platform catalogue (P17): `GET /platform/modules/`; `GET,POST /platform/feature-flags/` (upsert); `GET,POST /platform/plans/`, `GET,PATCH /platform/plans/{code}/` (name, visibility, limits, `trial_days`, modules, archive); `GET,POST /platform/addons/`; `GET,POST /platform/prices/` and `POST /platform/prices/{id}/deactivate/` (`billing.price.manage`, step-up). Amounts are validated and stored as entered; nothing is suggested or seeded |
| P25 | Tenant subscription (P18): `GET /platform/tenants/{id}/subscription/` (plan, add-ons, open overrides, modules resolved live); `POST …/plan/`, `…/trial/`, `…/addons/`, `…/addons/{code}/remove/`, `…/overrides/`, `…/overrides/{module}/end/` with a 10–200 character reason; `billing.subscription.manage` needs a fresh step-up. Unknown tenants and nothing-to-end answer 404 |
| P26 | Tenant host: `GET /tenant/subscription/` (`billing.subscription.view`, module `billing`): plan, status, add-ons, modules from the stored snapshot (what enforcement uses) and limits with current usage. Not served in restricted owner mode (the Phase 3 D2 list is unchanged) |
| P27 | `/me/context/` gains `entitlements`: enabled modules, flags evaluated for the tenant, limits with usage. The UI only hides what the server refuses |
| P28 | Every platform view declares its catalogue operation (P17/P18); the completeness test now covers the billing and module registry APIs. Reads list registry rows only; writes call the services (scope + uncached permission). OpenAPI regenerated with 0 warnings and the TypeScript client regenerated |

### Change notes
- 2026-11-21 — Created (Proposed).
- 2026-11-21 — Approved by the owner with the recommended answers (ADR-054).
- 2026-11-21 — §13.1 appended: M1 notes P1–P5.
- 2026-11-21 — §13.2 appended: M2 notes P6–P11.
- 2026-11-21 — §13.3 appended: M3 notes P12–P17.
- 2026-11-21 — §13.4 appended: M4 notes P18–P23.
- 2026-11-21 — §13.5 appended: M5 notes P24–P28.
