# Phase 4 — Security Self-Review (M7)

- **Scope:** module registry, billing data model, entitlement resolution and enforcement, the platform and tenant APIs, and the frontend of Phase 4 (M1–M7; plan `docs/plans/PHASE_04_PLAN.md`, ADR-050–054).
- **Method:**
  - code reading of every new path;
  - the automated gates (isolation registry, URL audit, catalogue completeness, host-route review);
  - targeted tests, including a threaded concurrency test.
- **Status:** self-review by the implementer. It is not an independent review and does not replace the owner's approval.
- **Tenant hosts remain disabled** in every committed configuration; they are enabled only in the throwaway CI/local E2E stack.

## 1. Defects found and fixed during Phase 4

| # | Defect | How it was found | Fix |
|---|---|---|---|
| F1 | The cached entitlement reader counted unbuilt platform modules (`files`, `notifications_core`) as enabled, disagreeing with the resolver | M3 tests | The reader uses the same "built" rule as the resolver |
| F2 | Two concurrent subscription changes for one tenant could both rewrite the snapshot (`module_registry_tm_unique` violation, failed change) | M7 threaded concurrency test | `recompute()` takes a transaction-scoped advisory lock per tenant and resolves after the lock, so the last recompute stores the latest committed state |
| F3 | A new docstring leaked into every tenant operation's public OpenAPI description | M4 OpenAPI drift check | Comments instead of docstrings on the mixin and base view |
| F4 | Two OpenAPI component name clashes (`ReasonRequest`, `LimitUsage`) that would have produced a wrong schema | M5 `--fail-on-warn` | Renamed and reused the shared serializer |

## 2. Review of the attack surface

| Area | Finding |
|---|---|
| **Entitlement enforcement** | `ModuleEntitled` runs before the permission check and fails closed: a gated view without a module is denied, and unknown codes fail at declaration. Platform modules pass without a lookup. Anonymous callers get `401` and learn nothing about entitlements. The URL audit requires an installed `module_code` on every tenant-reachable view and enforcement for non-platform modules. `tenant_task(module=…)` and `require_module()` cover tasks and services |
| **Entitlement data** | The snapshot (`module_registry_tenantmodule`) has standard tenant RLS and is written only inside the tenant's own transaction (asserted). The cache key is tenant-prefixed and versioned and is bumped on every recompute. Unbuilt modules are never enabled, even when granted. A broken dependency disables the dependent module and never enables the dependency |
| **Billing registry** | Subscriptions, items and overrides are self-scoped with tenant writes forbidden: a tenant reads only its own rows (raw-SQL tests as `erp_app`). The catalogue tables (plans, add-ons, prices, flags) carry no tenant data and keep runtime DML grants, because P17 writes run as `erp_app` (no owner credentials at runtime). Their protection is the service layer: `platform_scope` P17 with an uncached permission check. The module catalogue stays SELECT-only for the runtime role |
| **Platform operations** | Every platform view declares P17/P18 (completeness test). Writes call services that open the catalogued scope and re-check the permission without the cache. Subscription and price changes need a fresh step-up. All billing codes need MFA. Subscription changes need a 10–200 character reason and write both the platform and the tenant audit logs. The P19 sweep and the usage metering run as system iterations; per-tenant work runs in tenant tasks |
| **Prices** | Never seeded or edited. A new price deactivates the previous active one. `NUMERIC(18,2)`, ISO-4217 check, never negative. The frontend sends the amount as typed (string) and suggests nothing |
| **Feature flags** | Data only. Rules are validated (percentage 0–100, plan codes, tenant UUIDs, at most 500 entries); there is no expression evaluation and no per-tenant code path |
| **Denials** | `module_not_entitled` refusals are audited (`authz.denied` with the module), aggregated per actor and module per minute, and written durably on tenant hosts |
| **Restricted owner mode (D2)** | Unchanged: the new tenant subscription page is not served on suspended tenants |
| **Platform support** | No billing access (no billing codes; the H2 rule protects `platform_billing` holders); `billing.subscription.view` is support-readable on the tenant host only through an approved support session |
| **Frontend** | Navigation needs both the permission and the module; hidden is not secure. No credentials in storage; step-up recovery on every privileged action |

## 3. Residual risks and open items (for the owner)

1. **Expiry lag up to one hour.** Enforcement uses the stored snapshot. A trial, add-on or override that ends between two hourly P19 sweeps stays effective until the next sweep (at most about 60 minutes). This is an accepted design trade-off; a shorter beat interval is a configuration change.
2. **Trial at provisioning fails soft.** If starting the `trial` plan fails, the error is logged and the tenant keeps platform modules only. This is safe (fail closed for modules), but needs monitoring once alerting exists (Phase 18).
3. **Catalogue tables are writable by the runtime role.** This is necessary while P17 runs at runtime without owner credentials. The mitigations are the service layer, the uncached permission checks and the audit log. A database-level split (definer functions) can be considered in Phase 18.
4. **Not built in Phase 4:**
   - per-module localised names (modules are shown as codes);
   - `valid_from`/`valid_until` on the snapshot (validity lives on items and overrides instead).
5. **Still open from Phase 3:**
   - re-checking the inviter's permission at invitation acceptance (owner decision);
   - the items moved to Phase 18 (D9 benchmark, prefork K6, alerting, tenant-list pagination).

### Change notes
- 2026-11-21 — Created (Phase 4 M7).
