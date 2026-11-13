# Phase 3 — Milestone M3 Implementation Plan: Host Policy, Tenant Request Lifecycle and Durable Audit

- **Status:** **Approved** (owner, 2026-11-13, with the answers to §8 recorded in ADR-048) and **implemented** on `feat/phase-03-m3`; see §11 for what was built, what deviates and what is deferred. The text of §1–§10 is kept as proposed.
- **Phase:** 3 — SaaS tenants, institutions and campuses (plan `PHASE_03_PLAN.md` rev. 3, **Approved**; ADR-041–047 **Accepted**).
- **Milestone:** M3 (after M1 `3108824` and M2 `3616778`, both merged).
- **Planned branch:** `feat/phase-03-m3` (created only after this plan is approved). This document lives on `docs/phase-03-m3-plan`.
- **Basis:** `PHASE_03_PLAN.md` §6.3, §7, §8, §10, §12.4, §15, §20, §21, §24 and decisions D1–D9. This plan **adds detail only**. Where the approved plan is silent or ambiguous, the point is listed in §8 for the owner to decide. No approved decision is changed here.

---

## 1. Goal and boundaries

M3 turns the isolation primitives of M1 and the tenant registry of M2 into a **safe request path**: the server decides, from the `Host` header alone, whether a request is a platform request, a tenant request or a uniform 404; tenant requests run in one tenant transaction; failures roll back; and the evidence of denials survives the rollback.

**Approved M3 deliverables** (`PHASE_03_PLAN.md` §20, verbatim scope):

1. Host policy and `TenantResolutionMiddleware`.
2. Tenant transaction middleware, rollback on error, performance safeguards (`lock_timeout`, `tx_ms`, streaming refusal).
3. Durable-audit connection alias (`audit_durable`).
4. `TENANT_HOSTS_ENABLED` gate and production guard.
5. Generic sign-in error on tenant hosts (D7).
6. `CONN_MAX_AGE = 0` for every runtime alias and a connection measurement under ASGI (D4).
7. `ScopeTargetMiddleware` retired.

**Exit evidence (§20):** host decision-table tests; R1–R9; L1–L10; K1, K2 (also in forced-reuse mode), K8; config-guard tests; D4 measurement recorded.

**Explicitly not in M3** (owner constraints and later milestones):

| Not in M3 | Where |
|---|---|
| Enabling tenant hosts in production, choosing any real domain | D1: deferred until the owner supplies the domain and approves the Phase 3 security review |
| Runtime `BYPASSRLS`, break-glass, any change to `erp_platform` | ADR-043, D6 |
| Membership/invitation services, role assignments, `TenantMembershipSource` | M4 |
| Support sessions, `SupportSessionSource`, suspended-tenant restricted mode for owners | M5 |
| Dual-scope RLS on `rbac_role`, `rbac_rolepermission`, `audit_auditevent`, `audit_auditeventip` | M6 |
| `TenantTask`, cache/storage key helpers, Celery leak tests C1–C10, K6 | M7 |
| Tenant/platform tenancy APIs, OpenAPI additions, URL-audit host metadata for new endpoints | M8 |
| Frontend | M9 |
| Isolation benchmark against D9, K3 full-stack test | M10 |

---

## 2. Verified current state (inspected in code on `main` = `e23ba29`)

| Area | Fact |
|---|---|
| Middleware | `RequestID → Security → Session → Common → CSRF → Auth → SessionSecurity → ScopeTargetMiddleware → ApiNoStore → XFrameOptions` (`config/settings/base.py:43`). `ScopeTargetMiddleware` sets `request.scope_target = PLATFORM` for every request. |
| Scope consumers | `apps/rbac/permissions.py` and two views read `request.scope_target`; they default to `PLATFORM`. `ScopeTarget` already has `tenant_id/institution_id/campus_id` and a tenant-prefixed cache key. |
| Hosts | `ALLOWED_HOSTS` from env; dev allows `.localhost`; **any allowed host is treated as the platform** (ADR-040 I2 gap). No `PLATFORM_HOSTS`, `TENANT_BASE_DOMAIN` or `TENANT_HOSTS_ENABLED` setting exists. |
| Sessions | `SessionRecord.host` already stores `request.get_host()[:255]` (**raw, may include a port**). Cookies are host-only; `__Host-` prefix in production. |
| Database | `CONN_MAX_AGE` default **60** from `DATABASE_CONN_MAX_AGE`; `CONN_HEALTH_CHECKS=True`; `ATOMIC_REQUESTS=False`. Only the `default` alias exists in runtime settings (the test settings add `isolation_secondary`). |
| Tenant primitives (M1) | `tenant_atomic`, per-connection query guard, `TenantScopedModel`, `platform_scope` with catalogue P1–P16, request/task boundary leak checks (`apps/core/tenancy/boundaries.py`). **No `lock_timeout`, no request middleware** (N13). |
| Tenancy app (M2) | Models, F1–F3 via `apps/tenancy/selectors/platform.py`. P1 is catalogued as anonymous, mechanism D, `audited=False`. No URLs/views. |
| Audit | `audit.record()` writes on the caller's connection, in the caller's transaction (N12). No `durable` option. `authz.denied` is emitted once per minute per user/code from `apps/rbac/permissions.py:47`. |
| Sign-in | `login_with_password` + `EmailBackend` already hash a dummy password for unknown or unactivated users (timing equalisation). Failures raise one `InvalidCredentials`. |
| Frontend → API | The Next.js server calls `API_INTERNAL_URL=http://api:8000`, so the `Host` seen by Django for server-side calls is **`api`** unless the host is forwarded. Dev `ALLOWED_HOSTS` already contains `api`. |
| Nginx | Passes `Host $host`, sets `X-Real-IP`; `server_name _`. No change needed for M3. |

---

## 3. Work packages

Each package lists the design, the files, and the tests. File names are proposals within the existing layout (`models → selectors → services → …`, import contracts unchanged).

### M3-A Configuration, guards and `CONN_MAX_AGE = 0` (D1, D4)

**Settings** (`config/settings/base.py`; values per `PHASE_03_PLAN.md` §10.2–10.3):

| Setting | Default | Notes |
|---|---|---|
| `PLATFORM_HOSTS` | dev: `localhost,127.0.0.1,api`; test: `testserver,localhost`; **prod: none** (refuses to start if empty) | Normalised (lower-case, no port). |
| `TENANT_BASE_DOMAIN` | dev: `localhost`; test: `tenants.test`; prod: none | Tenant host = exactly `<slug>.<base>`. |
| `TENANT_HOSTS_ENABLED` | **`false` in every environment** | Test fixtures and dev `.env` switch it on explicitly. |
| `DATABASE_CONN_MAX_AGE` | **`0`** (was 60) | Applies to `default` and `audit_durable`; Celery uses the same settings. `CONN_HEALTH_CHECKS=True` kept. |

**Config guards** (`apps/core/config_guards.py`, same style as ADR-040 H3):

1. `TENANT_HOSTS_ENABLED=true` in production requires `TENANT_BASE_DOMAIN` set and **not** a placeholder/reserved name: `localhost`, `*.test`, `*.example`, `*.invalid`, `*.local`, `example.com/.net/.org`.
2. Production requires non-empty `PLATFORM_HOSTS`, each covered by `ALLOWED_HOSTS`.
3. Production refuses `DATABASE_CONN_MAX_AGE != 0` (D4: any persistent-connection setting needs owner approval and leak tests; changing this guard is that approval step).
4. A platform host may not look like a tenant host unless its label is a reserved slug (e.g. `admin.<domain>` is fine because `admin` is reserved) — keeps host classes unambiguous.

**Files:** `config/settings/{base,dev,test,prod}.py`, `apps/core/config_guards.py`, `.env.example`, `docker-compose.yml` (pass new variables to `api`), `docs/DOCKER_DEPLOYMENT.md`.
**Tests:** guard unit tests (each rule, accept and reject); settings test asserting `CONN_MAX_AGE == 0` on all runtime aliases and that tenant hosts are off by default in every settings module.

### M3-B Host policy (decision table, D1, ADR-041)

A **pure function** `classify_host(raw_host, config) -> HostDecision` in `apps/tenancy/hosts.py`, no I/O, exhaustively table-tested.

Normalisation: lower-case; strip port; reject empty, non-ASCII, underscore, trailing-dot-only, IP literals (v4, bracketed v6) for tenant matching.

| Step | Condition | Result | DB access |
|---|---|---|---|
| 0 | Path `/healthz`, `/readyz` | Pass through, no session/tenant | readiness `SELECT 1` only |
| 1 | Host fails `ALLOWED_HOSTS` | `400` (Django) | none |
| 2 | Host ∈ `PLATFORM_HOSTS` | Platform | none |
| 3 | `TENANT_HOSTS_ENABLED=false` | uniform `404 not_found` | **none** |
| 4 | Not exactly `<slug>.<TENANT_BASE_DOMAIN>`, IP literal, non-ASCII | uniform `404` | none |
| 5 | F1 returns no row (unknown, provisioning, deleted) | uniform `404` | F1 |
| 6 | Row found (active, suspended, offboarding) | Tenant | F1 |

The 404 is the Problem Details `not_found` body with the same headers and status for steps 3–5. `X-Tenant` headers and ids in bodies/queries are ignored for tenant choice.

### M3-C `TenantResolutionMiddleware` (P1) and scope target

- Calls F1 through `platform_scope("P1", anonymous)` in autocommit (no tenant context exists yet). **No caching of F1 results**: a suspension or deletion must take effect on the next request (cost: one indexed lookup per tenant-host request).
- Sets `request.host_kind` (`platform` | `tenant`), `request.tenant` (a `TenantContext`), and **`request.scope_target`** (`PLATFORM` or `ScopeTarget(tenant_id=…)`).
- **Retires `ScopeTargetMiddleware`**: remove `apps/rbac/middleware.py` and its settings entry; views and permission classes are unchanged (they already read `request.scope_target`).
- **Default deny for tenant hosts:** with no tenant RBAC sources until M4, every permission check on a tenant host returns nothing. A test asserts that a `super_admin` calling any permission-protected endpoint on a tenant host gets 403 (platform roles have no implicit tenant-data access, ADR-031/037).
- **Session-host binding:** a session whose `SessionRecord.host` (normalised: lower-case, port stripped — Phase 2 rows may contain ports) differs from the request host is treated as **anonymous** and a `tenancy.isolation.blocked` event is recorded; the session is **not** revoked (no denial-of-service by replaying a cookie). The comparison uses the record `SessionSecurityMiddleware` already loads, so there is no extra query.
- Host-class metadata: see M3-F.

### M3-D Tenant transaction middleware, rollback and safeguards (ADR-042, Q7, D9)

`TenantTransactionMiddleware`, **tenant hosts only**; platform hosts stay in autocommit exactly as in Phase 2.

```
RequestID → Security → [HostPolicy*] → Session → Common → CSRF → Auth → SessionSecurity
  → TenantResolution → TenantTransaction → ApiNoStore → XFrameOptions
```
`*` see §8 decision Q1.

Inside `tenant_atomic(ctx)`:

1. `set_config('lock_timeout','5s', true)` — implemented as a small additive parameter on `tenant_atomic` (`lock_timeout: str | None = None`) so the single helper stays the only entry point (N4).
2. **Gate** (see M3-E) before the view runs.
3. View → `HasPermission` → services.
4. If the response status is **≥ 400**, `transaction.set_rollback(True)`. The Problem Details handler never needs to know.
5. `StreamingHttpResponse`/`FileResponse` on a tenant host → replaced by a 500 Problem Details, logged and sent to Sentry (L7).
6. `finally`: contextvar reset (always). The M1 boundary leak check stays the backstop (raises under `TENANCY_LEAK_STRICT`, logs to Sentry in production).
7. `tx_ms` structured-log field on every tenant request; `warning` above **2 s**; Sentry span.
8. External I/O guard: the test email backend raises if called inside an open tenant transaction (the storage helper does not exist until M7; its guard is added there).

Session persistence stays outside the transaction (`SessionMiddleware.process_response` runs after the contextvar reset), as in `PHASE_03_PLAN.md` §8.2.

### M3-E Membership gate, tenant status, generic sign-in error (D2, D7)

Runs inside the tenant transaction, once per request, with **no caching** (revocation is effective on the next request).

| Condition | Result |
|---|---|
| Anonymous request | Allowed only for views declared anonymous-capable (M3-F); otherwise the view's own permission class returns 401 |
| Authenticated, no `Membership` row | `403 not_a_member` |
| Membership not `active` | `403 membership_inactive` |
| Tenant `suspended` | `403 tenant_suspended` for every request, **including owners**, until M5 adds the owner restricted mode (D2). Fail closed. |
| Tenant `offboarding` | unsafe methods `403 tenant_unavailable`; reads follow normal rules (owner-only access arrives with M4 roles) |
| Active support session | **Not recognised in M3** — a staff member without membership gets `not_a_member`. M5 adds `SupportSessionSource`. |

**Sign-in on a tenant host (D7):** after the password check passes, the service checks for an active membership of that tenant and an `active` tenant. A non-member, unknown email, wrong password, suspended/left membership, and any sign-in on a suspended tenant all raise the **same** `InvalidCredentials` (same body, status, code), counted by the same throttle buckets, using the Phase 2 dummy-hash path for timing. The internal audit event records the real reason (`not_a_member`, `tenant_suspended`, …) as durable evidence in the tenant log; the client never sees it. Residual timing differences between "wrong password" and "right password, not a member" are small next to the Argon2 cost; this is stated, tested for status/body equality, and not claimed to be perfectly constant-time.

### M3-F Which existing endpoints are reachable on tenant hosts (host-class metadata)

The approved plan says a view is platform-only or tenant-only (§12) and that the full URL audit arrives in M8, but M3 already opens tenant hosts, so a **minimal, fail-closed** mechanism is needed now:

- View attribute `host_classes: frozenset[Literal["platform","tenant"]]`; **a view with no declaration is platform-only** and returns the uniform 404 on tenant hosts.
- Declared `{"platform","tenant"}` in M3 (proposal, §8 Q2): `login`, MFA challenge/verify, `logout`, CSRF bootstrap, `me`. Platform admin endpoints (users, roles, audit, sessions admin) and account recovery/activation stay **platform-only**; recovery links point to the platform host, sign-in then happens on the tenant host with the same credentials.
- A test enumerates the URL conf and fails if a view lacks a declaration.

### M3-G Durable audit alias (ADR-042, owner requirement 5)

- `DATABASES["audit_durable"]`: same `erp_app` credentials (no new role, no new dependency), `CONN_MAX_AGE=0`, `ATOMIC_REQUESTS=False`. Test settings mirror the test database like `isolation_secondary`; `conftest.py` applies the same role switch.
- `audit.record(..., durable: bool = False)`: writes with `.using("audit_durable")` inside its own `tenant_atomic(tenant, using="audit_durable")` (or a plain atomic when there is no tenant), so the row carries the right `tenant_id` and the per-connection guard keeps the two connections independent.
- A central `DURABLE_ACTIONS` set in `apps/audit/events.py`: `authz.denied`, `identity.login.failed`, `identity.login.locked`, `tenancy.isolation.blocked` now; `support.access_denied`, `support.write_rejected`, `invitation.invalid_attempt` registered when M5/M4 add them. When a tenant context is active the set forces the durable path, so **Phase 2 call sites do not change**. Platform-host behaviour is unchanged (R7).
- `tenancy.isolation.blocked` is written **durably to the platform log** with the tenant id as metadata only (P14), covering guard violations, session-host mismatches and tenant conflicts.
- **Failure policy:** if the durable write fails, the response stays a denial (fail closed); the failure is logged with `request_id` and sent to Sentry; a denial is never turned into success.
- Durable events reference only already-committed identifiers (actor user id, tenant id, request id).
- `tenancy.host.rejected` is a sampled structured log and a counter, **not** a database write (disabled mode must perform no lookup).

### M3-H D4 measurement

- A stdlib-threads measurement script (`infra/scripts/measure_db_connections.py`, per the §8.4 methodology: 200 warm-up, 2 000 measured requests, concurrency 1/8/32, 3 repetitions, p50/p95/p99, environment recorded) against the compose stack through Nginx and Uvicorn.
- Compares `DATABASE_CONN_MAX_AGE=0` against a non-production control (`60`) for connection-setup cost, request latency and connection counts (`pg_stat_activity`).
- Results go to `docs/benchmarks/PHASE_03_CONNECTIONS.md`. If the cost is material, **the owner decides** (per `PHASE_03_PLAN.md` risk table) whether to propose persistent connections or a pool; nothing changes without approval, leak tests and (for a pool library) dependency approval.
- The tenant-host path is measured once a tenant exists in the disposable measurement database; the isolation-overhead benchmark against D9 remains M10.

---

## 4. Test plan

All new tests run as `erp_app` on PostgreSQL 17. Commit-dependent tests follow N10 (worker threads with their own connections, cleaned up). Tenant-host behaviour is exercised through a **test-only URL conf and probe views** in `tests.isolation_app` (no production endpoint is added).

| Group | Tests |
|---|---|
| Host policy | Table-driven: every step 0–6, ports, case, trailing dot, IPv4/IPv6 literals, non-ASCII, underscores, `*.localhost`, platform vs tenant overlap; unknown/provisioning/deleted produce **identical** responses; step 3 performs zero queries (query-count assertion) |
| Resolution | Tenant chosen only from host (`X-Tenant`, body, query ignored); suspended/offboarding resolve; session-host mismatch → anonymous + durable platform event; Phase 2 sessions with ports still match |
| **R1–R9** | R1 rollback + durable `authz.denied`; R2 durable event has the right `tenant_id`; R3 durable connection cannot see uncommitted rows; R4 durable write failure keeps 403; R5 `on_commit` side effects only after commit; R6 savepoint partial rollback; R7 handler/rollback only inside tenant tx, platform unchanged; R8 unhandled exception leaves no data and no open tx, next request works. See §5 for R2 and R9 limits. |
| **L1–L10** | L1 forced persistent connection serves A then B; L2 exception; L3 platform request after tenant request on same thread/connection; L4 `on_commit` guard; L5 new thread; L6 durable alias separate marker; L7 streaming refused; L8 leak detector; L9 concurrent requests through the ASGI app (see §5); L10 static check for session-level `SET`/`SET ROLE`. |
| Concurrency | **K1** 20 threads × 50 requests alternating 3 tenant hosts; **K2** one thread, one forced persistent connection, sequence A, B, A, platform, B with equal `pg_backend_pid()` and empty `current_setting` between requests (both also with `CONN_MAX_AGE>0` forced-reuse); **K8** platform requests interleaved with tenant requests |
| Sign-in (D7) | Non-member, unknown email, wrong password, suspended/left membership, suspended tenant → identical status/body/code; throttle counting identical; audit reason differs only internally |
| Gate | not_a_member, membership_inactive, tenant_suspended (including owner, until M5), tenant_unavailable on offboarding writes; super_admin gets 403 on tenant hosts |
| Config guards | Every rule in M3-A, accept and reject; defaults off in every settings module |
| Compatibility | The entire Phase 2 suite, E2E and CI jobs stay green; platform-host behaviour is byte-for-byte unchanged |
| Static/CI | Host-class completeness test; import contracts (9/9) unchanged or extended only for `apps.tenancy` ↔ `apps.audit`; `check_runtime_secrets` unchanged |

---

## 5. Items that cannot be fully verified in M3 (stated up front, not hidden)

| Item | Why | Plan |
|---|---|---|
| **R2** "invisible from another tenant" | `audit_auditevent` has no RLS until M6 (N6); M3 can prove the **tenant id is correct**, not cross-tenant invisibility | Correct-`tenant_id` assertion in M3; invisibility assertion added in M6 (policy tests on the real tables) |
| **R9** support-session read audited atomically | Support sessions are M5 | Implemented with S4 in M5 |
| **K3 / L9 through Nginx/Uvicorn** | Full-stack test is an M10 deliverable (§15.3) | M3 adds an in-process ASGI concurrency test for L9; K3 stays in M10 |
| Email guard yes, **storage guard no** | No storage helper exists until M7 | Added with the helper |
| Suspended-tenant **owner restricted mode**, owner-only offboarding access | Needs role assignments (M4) and support-session endpoints (M5) | M3 fails closed (everyone is denied) |

---

## 6. Migrations, grants, dependencies, security review

- **Migrations: none expected.** The durable alias uses the same database and role. No new table, grant, role, `SECURITY DEFINER` function or credential.
- **Dependencies: none.** (stdlib threads for measurement; no pool library.)
- **Security notes for the PR:** no `BYPASSRLS`; `erp_platform` untouched; tenant hosts stay off by default and in production until the owner provides the domain and approves the security review (D1); failures are fail-closed; no cross-tenant lists (D8); no platform-host view of tenant audit events (D3).
- **Docs updated in the M3 PR:** `MULTI_TENANT_ARCHITECTURE.md`, `SECURITY.md`, `API_STANDARDS.md` (uniform 404, new error handling), `DOCKER_DEPLOYMENT.md` and `.env.example` (new variables), `PHASE_03_PLAN.md` §24.6 (M3 notes), `DEVELOPMENT_PROGRESS.md`, `benchmarks/PHASE_03_CONNECTIONS.md`.

---

## 7. Implementation order (each step committed with tests, lint, types green)

1. **M3-A** settings, guards, `CONN_MAX_AGE=0`, new env variables.
2. **M3-B** `classify_host` + exhaustive table tests (pure code).
3. **M3-G** `audit_durable` alias, `durable` option, `DURABLE_ACTIONS`, failure policy, R3/R4/L6.
4. **M3-C** `TenantResolutionMiddleware`, scope target, retire `ScopeTargetMiddleware`, session-host binding.
5. **M3-D** `TenantTransactionMiddleware`, `lock_timeout`, rollback, streaming refusal, `tx_ms`, email guard; R1/R2/R5–R8, L1–L5, L7, L8, L10.
6. **M3-F** host-class metadata and completeness test.
7. **M3-E** membership/status gate and tenant-host sign-in (D7).
8. K1, K2, K8 and forced-reuse runs; L9 in-process ASGI test.
9. **M3-H** measurement run and recorded results.
10. Docs, progress, full verification (pytest + coverage, ruff, mypy, import-linter, `makemigrations --check`, OpenAPI drift, Docker clean-volume bootstrap, smoke, Playwright, gitleaks, Trivy), then a **separate PR**. **Not merged without owner approval.**

---

## 8. Decisions requested from the owner

Each item has a recommendation. None changes an approved decision; each fills a gap or refines wording in `PHASE_03_PLAN.md`.

| # | Question | Recommendation |
|---|---|---|
| **Q1** | `PHASE_03_PLAN.md` §8.2 lists one resolution middleware after `SessionSecurity`, while §10.1 and acceptance 5 say disabled mode performs no tenant lookup. Authenticated-session handling (a session-store and identity read) would otherwise run **before** the host is rejected. Split into a pure `HostPolicyMiddleware` placed **before** `Session` (steps 0–4, no I/O) and `TenantResolutionMiddleware` after `SessionSecurity` (step 5–6, session-host binding, scope)? | **Yes, split.** Strictly stronger: rejected hosts touch neither the session store nor the database. |
| **Q2** | Which Phase 2 endpoints are reachable on tenant hosts in M3 (§12 requires platform-only/tenant-only metadata, full audit in M8)? | **Minimal:** login, MFA challenge/verify, logout, CSRF bootstrap, `me`. Everything else (admin, audit, account recovery, activation) stays platform-only; recovery links point to the platform host. |
| **Q3** | `PHASE_03_PLAN.md` §10.3 gives dev `PLATFORM_HOSTS = localhost,127.0.0.1`, but the Next.js server calls the API as host `api` (`API_INTERNAL_URL=http://api:8000`); with tenant hosts disabled that host would receive the uniform 404 and break server-side rendering. | Add the internal service host **`api`** to dev, CI and E2E `PLATFORM_HOSTS`; in production list the internal API host explicitly in `PLATFORM_HOSTS` (no default). Tenant-host SSR forwarding of the browser `Host` stays an M9 item. |
| **Q4** | Test items that depend on later milestones (§5): R2 invisibility → M6, R9 → M5, K3 → M10, storage guard → M7; L9 as an in-process ASGI test in M3. | **Accept** the split; each item is tracked in the progress file's known gaps. |
| **Q5** | Suspended/offboarding tenants in M3, before owner roles (M4) and the restricted mode (M5) exist. | **Fail closed:** suspended → 403 for everyone including owners; offboarding → no writes. Owner restricted mode (D2) is delivered in M5 exactly as approved. |
| **Q6** | `DATABASE_CONN_MAX_AGE`: keep an env override (needed for the non-production measurement control) with a **production guard** refusing non-zero, or hard-code 0? | **Keep the override plus the production guard.** Raising it in production then requires a reviewed code change, matching D4. |
| **Q7** | Where to record the D4 measurement and what counts as "material"? | `docs/benchmarks/PHASE_03_CONNECTIONS.md`; report numbers and let the owner judge — no automatic threshold, per D4. (The D9 20 % target applies to the M10 isolation-overhead benchmark.) |

---

## 9. Risks specific to M3

| Risk | Control |
|---|---|
| A middleware ordering mistake exposes tenant data or sessions across hosts | Decision-table tests; session-host binding; K1/K2/K8; default deny while no tenant RBAC source exists |
| Contextvar propagation differs under ASGI (sync middleware adapted to the executor) | L9 in-process ASGI test now; K3 through the real stack in M10; `CONN_MAX_AGE=0` from the start |
| Request-wide transactions hold locks or connections too long | `lock_timeout 5s`, existing `statement_timeout`/`idle_in_transaction_session_timeout`, `tx_ms` warnings, no external I/O inside the transaction |
| Durable-audit connection cost under error bursts | Only on denials/failures, bounded by existing throttles; measured in M3-H |
| Phase 2 behaviour regressions on the platform host | Platform requests stay in autocommit; the whole Phase 2 suite and E2E must stay green |
| Sign-in oracle on tenant hosts | One `InvalidCredentials` path, shared throttle buckets, dummy-hash timing, equality tests |
| Dev behaviour change (`*.localhost` is no longer the platform) | Documented in `.env.example` and the PR; dev switches `TENANT_HOSTS_ENABLED` on explicitly |

---

## 10. Approval gate

Implementation starts only after the owner approves this plan (or amends it through §8). The M3 branch is created from the then-current `main`; the PR is opened separately and is **not merged without explicit owner approval**. M4 is not started.

## 11. Owner decisions and implementation record (2026-11-13)

### 11.1 Owner answers to §8 (ADR-048)

| # | Answer |
|---|---|
| Q1 | Two stages: pure host policy before sessions; tenant resolution later |
| Q2 | Tenant hosts serve login, MFA, logout, CSRF and `me`; everything else platform-only |
| Q3 | `api` added to the development, CI and E2E platform hosts |
| Q4 | R2 invisibility → M6; R9 → M5; K3 → M10; storage guard → M7. Not marked as passed |
| Q5 | Suspended: fail closed for everyone; offboarding: no writes; D2 owner mode → M5 |
| Q6 | `CONN_MAX_AGE = 0` by default; non-production override; production rejects non-zero |
| Q7 | Results in `docs/benchmarks/PHASE_03_CONNECTIONS.md`; nothing invented, nothing relaxed automatically |

### 11.2 What was implemented

| Package | Implementation |
|---|---|
| M3-A | `PLATFORM_HOSTS`, `TENANT_BASE_DOMAIN`, `TENANT_HOSTS_ENABLED` (default `false` in every settings module), `DATABASE_CONN_MAX_AGE` default 0; `core.config_guards.assert_host_configuration` and `assert_no_persistent_connections` |
| M3-B | `apps/tenancy/hosts.py` `classify_host` (pure) and `core.net.normalize_host` |
| M3-C | `HostPolicyMiddleware` (before sessions) and `TenantResolutionMiddleware` (F1 through `platform_scope("P1")`, never cached; session-host binding; `request.tenant`, `request.scope_target`). `apps/rbac/middleware.py` (`ScopeTargetMiddleware`) removed |
| M3-D | `TenantTransactionMiddleware`: `tenant_atomic(tenant, lock_timeout="5s")`, rollback for status ≥ 400, streaming bodies refused with a 500, `tx_ms` log with a warning above 2 s. `tenant_atomic` gained the `lock_timeout` argument |
| M3-E | `apps/tenancy/access.py`: request gate (`tenant_suspended`, `not_a_member`, `membership_inactive`, `tenant_unavailable`) and the sign-in guard behind `IDENTITY_SIGN_IN_GUARDS` (D7) |
| M3-F | `apps/core/hosts.py`: `host_classes` on views, platform-only by default; reviewed allow-list test `tests/test_host_classes.py` |
| M3-G | `audit_durable` alias; `audit.record(..., durable=…)`; `DURABLE_ACTIONS`; `tenancy.isolation.blocked` |
| M3-H | `infra/scripts/measure_db_connections.py`; results in `docs/benchmarks/PHASE_03_CONNECTIONS.md` |

### 11.3 Clarifications and deviations from §3–§4 (none changes an approved decision)

| # | Item | What was done | Why |
|---|---|---|---|
| I1 | Session-host mismatch | The request continues as anonymous with a fresh empty session, so the misplaced cookie is dropped on that host only; the stored session is untouched. One `tenancy.isolation.blocked` event in the platform log | Replaying a cookie on another host must not sign the real user out |
| I2 | `X-Forwarded-Host` | It stays trusted (`USE_X_FORWARDED_HOST`, Phase 1): Nginx overwrites it on every request and the Next.js server relays the browser host through it. It is therefore the request host and passes `ALLOWED_HOSTS` and the whole host policy. A test asserts the Nginx directive | The API container must never be reachable except through Nginx and the web service (already required for `X-Real-IP`). Recorded in `SECURITY.md` |
| I3 | Durable events | `DURABLE_ACTIONS` also contains `identity.login.throttled`, `identity.mfa.challenge_failed` and `identity.mfa.locked` | They are failure evidence of the same sign-in flow and would otherwise vanish with the rolled-back request |
| I4 | Tenant stamp | Inside a tenant context every audit event is stamped with that tenant unless the caller passes one. The platform audit API already lists only `tenant_id IS NULL` events (D3) | Tenant-host events belong to the tenant log; RLS on the audit tables follows in M6 |
| I5 | Isolation violations | A `TenantIsolationError` raised inside a tenant request is recorded after the transaction ended, in the platform log, with the tenant id as metadata only (P14) | The request transaction is rolled back; the platform log must not hold tenant data |
| I6 | Gate exemptions | Login, MFA verify, CSRF and logout skip the membership gate (`tenant_auth_flow`): sign-in is refused by the guard instead, and logout only ends the caller's own session, also on a suspended tenant | Otherwise D7 could not answer with the generic error, and a user could not sign out |
| I7 | Host-class test | Instead of requiring a declaration on every view, views default to platform-only and a reviewed allow-list test pins the exact set of tenant-reachable routes | Same fail-closed result with one reviewed place to change |
| I8 | Rollback rule | Implemented in the middleware (status ≥ 400), not in the Problem Details handler | Covers non-DRF responses too; platform hosts are untouched (R7) |
| I9 | Durable audit in tests | The alias is a second connection. Main-thread tests read it through the alias (it is wrapped in its own test transaction); worker-thread tests commit real, append-only events and find them by tenant id | Audit rows cannot be deleted; one Phase 2 assertion was scoped to its own actor for that reason |
| I10 | Forced-reuse mode | The Django test client keeps a thread's connection open between requests, so K1, K2 and K8 run every request of a thread on one physical connection (asserted with `pg_backend_pid()`) | This is the persistent-connection case D4 guards against |

### 11.4 Test status against §4 (actual, local)

| Item | Status |
|---|---|
| Host decision table (steps 0–6), disabled mode with zero queries, uniform 404 | **Pass** |
| R1, R3, R4, R5, R6, R7, R8 | **Pass** |
| R2 | **Partial:** the durable event carries the right `tenant_id`. Cross-tenant invisibility is **not tested**: the audit tables get RLS in M6 |
| R9 | **Not implemented** (support sessions, M5) |
| L1, L2, L3, L6, L7 | **Pass** (request level) |
| L4, L5, L8, L10 | **Pass** at the primitive level (M1 suites, unchanged); L8 also asserted after failed requests |
| L9 | **Pass** in process through Django's ASGI handler. The Nginx/Uvicorn stack test is K3 |
| K1, K2, K8 | **Pass**, in forced-reuse mode (I10) |
| K3 | **Not implemented** (M10) |
| Config guards, defaults off in every settings module, `CONN_MAX_AGE = 0` | **Pass** |
| D7 sign-in equality, shared throttles | **Pass** |
| External-I/O guard: email | **Not implemented.** Security emails are queued through Celery, which runs inline in tests, so a guard in the email backend would misfire. It moves to M7 with `TenantTask` / `@platform_task` |
| External-I/O guard: storage | **Not implemented** (no storage helper before M7) |

### 11.5 Open follow-ups

- M4: owner-only access during offboarding; tenant RBAC sources (until then nobody holds a tenant permission on a tenant host).
- M5: owner restricted mode for suspended tenants (D2); support sessions; R9; align `role_templates.py:36`.
- M6: RLS on the audit tables and the R2 invisibility test.
- M7: external-I/O guards; `TenantTask`.
- M9: tenant-host pages in the frontend (the Next.js server already relays the browser host).
- M10: K3 and the isolation-overhead benchmark against D9.

### Change notes
- 2026-11-09 — Initial proposal (status **Proposed**).
- 2026-11-13 — Owner answered §8 (ADR-048); plan Approved and implemented; §11 added.
