# Phase 5 — Security Self-Review (M8)

- **Scope:** everything Phase 5 added (M1–M8; plan `docs/plans/PHASE_05_PLAN.md`; ADR-055–061):
  - configuration versions and the resolver;
  - presets;
  - the rules sandbox;
  - custom fields;
  - forms, workflows and notifications;
  - the template sandbox and numbering;
  - the Studio APIs and UI;
  - self-service sign-up.
- **Method:**
  - I read every new code path.
  - The automated gates ran: isolation registry, RLS coverage, URL authorization audit, catalogue completeness, host-route review and the migration rehearsal.
  - Targeted tests ran, including the sandbox abuse cases and the threaded concurrency tests.
  - The real-stack E2E runs are listed in `DEVELOPMENT_PROGRESS.md`.
- **Status:** this is a self-review by the implementer. It is not an independent review and does not replace the owner's approval.
- **Tenant hosts:**
  - Tenant hosts stay disabled in every committed configuration.
  - Tenant hosts and sign-up are enabled only in the throwaway CI/local E2E stack.

## 1. Defects found and fixed during Phase 5

| # | Defect | How it was found | Fix |
|---|---|---|---|
| F1 | A choice field could be defined with no options | M3 tests | `define_field` always validates the options |
| F2 | The rule-test endpoint skipped the static check when there were no test cases | M6 API test | The endpoint runs `check(rule, spec)` first |
| F3 | A NOT NULL `extra` column broke raw SQL inserts (definer functions) | M6 tests | The column also has a database default of `'{}'::jsonb` |
| F4 | A concurrency test swallowed thread errors | M5 review | The test helper collects and re-raises the errors |
| F5 | Saving Studio settings dropped keys the screen does not edit (for example capability flags) | M7 review | The draft starts from the current document. Cleared keys are removed so the scope inherits them. This is unit-tested |
| F6 | The sign-up registry FK was called `tenant`. Its `tenant_id` column made the row look like tenant data | M8 isolation gates | The FK was renamed `provisioned_tenant` |

## 2. Review of the attack surface

| Area | Finding |
|---|---|
| **Tenant isolation** | <ul><li>Every new tenant table uses standard RLS (ENABLE + FORCE).</li><li>Child rows use composite tenant keys.</li><li>Isolation migrations cannot be reversed.</li><li>Presets and sign-up requests are allow-listed registry tables, each with a justification and tests.</li><li>Presets are SELECT-only for the runtime role.</li><li>No runtime `BYPASSRLS` was introduced, and no runtime service holds owner credentials.</li></ul> |
| **Rules (ADR-055)** | <ul><li>Rules are data, not code: 22 allow-listed operators.</li><li>Limits: 500 nodes, depth 32 and 10 000 steps.</li><li>`Decimal` arithmetic.</li><li>Variables come only from declared namespaces.</li><li>A rule that cannot decide hides its form section (fail closed).</li><li>Publishing requires passing test cases.</li></ul> |
| **Templates (ADR-056)** | <ul><li>Jinja2 `ImmutableSandboxedEnvironment`: no loader, no globals, allow-listed filters only, `StrictUndefined`.</li><li>The context is plain data with size and output limits.</li><li>The abuse tests cover dunder and `__globals__` access, `attr`, `range(10**9)`, `include`/`import`/`extends`, and the output and data size limits.</li></ul> |
| **Custom fields** | <ul><li>Values are validated against the definitions.</li><li>Edits need the field's `edit_permission` in the object's scope.</li><li>Reads are masked by `view_permission`. Without a request context, nothing is shown.</li></ul> |
| **Workflows** | <ul><li>Each transition needs its own permission.</li><li>Guards run in the sandbox.</li><li>A running instance stays on the definition version it started with.</li><li>History is append-only.</li><li>The SLA sweep (P24) runs per tenant.</li></ul> |
| **Numbering** | Numbers are gap-free, allocated under a row-locked counter inside the business transaction, and concurrency-tested. |
| **Studio API and UI** | <ul><li>Every view declares the module and its permission.</li><li>The services re-check the exact scope without the cache.</li><li>Publishing needs `customization.config.publish` (MFA plus a fresh step-up).</li><li>A configuration scope outside the viewer's scopes answers 404.</li><li>Quotas are enforced on the server.</li><li>The UI hides what the API forbids, but hiding is not the protection.</li><li>The browser never evaluates rules.</li></ul> |
| **Sign-up (P23, ADR-061)** | <ul><li>Off unless `TENANCY_SIGNUP_ENABLED` is set. While off, every route answers 404 before any validation.</li><li>The response is the same whatever the email (no enumeration).</li><li>A per-IP limit answers 429. The per-email limit is silent.</li><li>A filled honeypot field makes the request a silent no-op.</li><li>Only the SHA-256 hash of the single-use token is stored. The token travels in the URL fragment and expires after 48 hours.</li><li>The verify page needs a click, so mail scanners cannot confirm a request on someone's behalf.</li><li>The audit metadata never contains the email.</li><li>**No tenant exists without an administrator's decision:** approval runs P4 with the administrator as the actor.</li><li>A conditional state change stops two concurrent approvals from both proceeding.</li><li>A failed provisioning returns the request to `verified`.</li><li>Closed requests are deleted after 30 days (P25).</li></ul> |

## 3. Residual risks and open items (for the owner)

1. ~~**ADR-061 is Proposed.**~~ Accepted by the owner on 2026-11-23: sign-up approval is mandatory in v1.
2. **One client address in E2E.** The CI/local stack reaches the API from one Docker gateway address, so the per-IP sign-up limit (5 per hour) is shared by the whole E2E run. Production sees real client addresses through Nginx.
3. **Preset content is a draft** (ADR-060 Q4). It must be validated with real institutions before it is used for onboarding.
4. **JSON editors in Studio v1.** The editors are safe, because the server validates everything, but they are not friendly for non-technical admins. Visual builders are not built.
5. **Not built in Phase 5:**
   - custom field values on members (Phase 7);
   - SMS and push notifications (Phase 14);
   - dashboard and report-layout configuration (Phase 15).
6. **Still open from earlier phases:**
   - ~~re-checking the inviter's permission at invitation acceptance~~ — done on 2026-11-23 (ADR-062);
   - the items moved to Phase 18 (D9 benchmark, prefork K6, alerting).

### Change notes
- 2026-11-22 — Created (Phase 5 M8).
- 2026-11-23 — Owner approved Phase 5; ADR-061 Accepted; the inviter re-check (ADR-062) implemented.
