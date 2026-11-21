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

### Change notes
- 2026-11-21 — Created (Proposed).
- 2026-11-21 — Approved by the owner with the recommended answers (ADR-054).
