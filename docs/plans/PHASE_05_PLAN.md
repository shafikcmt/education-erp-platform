# Phase 5 Plan — Customization Studio and Institution Configuration

- **Status:** **Approved** (owner, 2026-11-22) with the recommended answers to Q1–Q5 (ADR-060). ADR-055 to ADR-059 Accepted.
- **Depends on:**
  - Phase 4 (**Approved** by the owner, 2026-11-22).
  - ADR-016 (rules engine), which this plan proposes to decide (ADR-055).
  - Accepted ADRs: ADR-009/043 (tenancy, platform operations), ADR-046 (RLS catalogue), ADR-050–054 (modules, entitlements, billing).
- **Roadmap scope (`DEVELOPMENT_ROADMAP.md` Phase 5):**
  - presets loader and initial presets for all six institution types;
  - config sets with versioning, publish and rollback;
  - effective config resolver and cache;
  - terminology;
  - custom field definitions and JSONB validation;
  - form definitions and the DynamicForm renderer;
  - workflow engine;
  - rules evaluator (sandboxed);
  - template engine (sandboxed) with preview;
  - numbering sequences;
  - Studio UI;
  - onboarding wizard;
  - minimal `notifications_core` (in-app and email).
- **Exit criteria:**
  - a tenant can be created per institution type from presets;
  - publish and rollback work;
  - the rule and template sandbox security tests pass.
- **Not in scope:**
  - custom entities (Phase 17);
  - PDF rendering (Phase 9, library to be verified for Bengali and Arabic shaping);
  - dashboards and report layouts (Phase 15);
  - SMS and push (Phase 14);
  - the modules that consume custom fields, forms and workflows (Phase 6 onwards). Phase 5 builds the frameworks and proves them with test entities and the existing tenancy entities.

## 1. Goals

1. **One codebase, configured.** Institution-type differences live in versioned presets (L2). Tenant differences live in versioned, published configuration (L3), never in code branches (CLAUDE.md §4).
2. **Resolution order:** core defaults → preset → tenant → institution → campus. Code reads configuration only through `get_effective_config(scope, "module.key")`. Every key is declared in a module's `settings_schema`; undeclared keys are rejected.
3. **Safety first:**
   - rules and templates run in sandboxes with allow-lists and resource limits;
   - no tenant-supplied executable code, ever;
   - security tests are part of the exit criteria.
4. **Everything Studio writes is:**
   - tenant-scoped (RLS);
   - permission-checked (`customization.*`);
   - validated server-side;
   - versioned (draft → published → archived);
   - audited with a diff.
5. **Usable on day one:** the onboarding wizard goes institution type → preset → modules (within entitlements) → branding.

## 2. Data model (proposed)

| Table | Owner | RLS class (ADR-046) | Notes |
|---|---|---|---|
| `customization_preset` | platform | registry allow-list | `code` (e.g. `madrasa.qawmi.v1`), institution type, version, content JSONB (validated), synced from repo files by an owner-run bootstrap (like `sync_modules`) |
| `tenancy_institution` (+ columns) | tenant | standard (existing) | `preset_code`, `preset_version` (pinned; additive migration) |
| `customization_configversion` | tenant | standard | scope (tenant / institution / campus), version number, status (`draft`/`published`/`archived`), `data` JSONB (declared keys only), author, published_at/by, change note |
| `customization_fielddefinition` | tenant | standard | entity (registry), key (immutable), labels (i18n), type, validation (JSON Schema subset), required, default, visibility, view/edit permission, PII flag, order, status |
| `customization_formdefinition` | tenant | standard | purpose, sections/steps, field references, visibility rules (rule AST), version, status |
| `customization_ruledefinition` | tenant | standard | namespace (registry), AST JSONB, test cases, version, status |
| `customization_workflowdefinition` | tenant | standard | subject (registry), states, transitions (guard rule, required permission, approver resolution), version, status |
| `customization_workflowinstance` / `…transition` | tenant | standard | pinned definition version, subject reference, state, history (append-only) |
| `customization_templatedefinition` | tenant | standard | kind (registry: receipt, ID card, SMS, email…), body, locale, version, status |
| `customization_numberingsequence` / `…counter` | tenant | standard | pattern tokens, scope, gap-free counters allocated under row lock |
| `notifications_core_notification` | tenant | standard | recipient membership, kind, payload (no secrets), read_at; email through the existing mail path |

All migrations are additive. Composite `(tenant_id, …)` keys are used for tenant-to-tenant references, as in Phase 3.

## 3. Configuration and versioning

- **Declared keys only:** each module manifest gains `settings_schema` (JSON Schema per key). It records the default, the allowed scopes, whether tenants may edit the key, the permission required, and the merge strategy.
- **Lifecycle:**
  - **Draft:** editable, visible only in Studio preview.
  - **Publish:** requires `customization.config.publish`, validation of the schema and references, rule test cases passing, an audit event with a diff, and a cache version bump. A published version is immutable.
  - **Rollback:** publishes a copy of an earlier version as a new version. History is never rewritten.
- **Records pin the version they depend on:** workflow instances, form submissions and rule-based computations keep the version they were created under.
- **Resolver cache:** keyed per (tenant, scope, config version); invalidated on publish.

## 4. Presets (L2)

- **Six initial presets:**
  - `school.general.v1`
  - `college.general.v1`
  - `university.credit.v1`
  - `madrasa.general.v1` (variants for Qawmi, Alia and Hifz expressed as data, never one board's rules hardcoded)
  - `coaching.general.v1`
  - `training.general.v1`
- **Preset content:** terminology (en, bn), structure-level labels, capability flags (e.g. `academics.credit_based`), suggested modules, default role labels, hostel profile reference.
- **Content is a draft for review.** Preset content is product data: it is drafted from `CUSTOMIZATION_ENGINE.md` §3 and must be validated with real institutions (question Q4).
- **Pinning:** institutions pin a preset version. A new preset version never changes existing tenants automatically; the upgrade is a reviewed opt-in.

## 5. Sandboxes (security-critical)

**Rules (ADR-055, decides ADR-016)** — a small in-house evaluator for a JSONLogic-style AST:
- allow-listed operators (comparison, boolean, arithmetic with `Decimal`, `in`, date difference, `if`);
- per-namespace context variables (e.g. `fees.late_fine` gets `invoice.balance`, `today`);
- no attribute access, loops, I/O or imports;
- limits on depth, node count and evaluation steps;
- deterministic results, no floats for money.
- Every namespace ships test cases, and Studio offers "test with sample data" before publish.

**Templates (ADR-056):** proposed Jinja2 `SandboxedEnvironment` with:
- autoescape on;
- context of plain dicts per template kind (never ORM objects);
- an allow-listed filter set and no `import` or `include`;
- render time and output size limits;
- preview with sample data.

**Security tests (exit criterion):**
- known escape payloads (`__class__`, `__globals__`, `mro`, format-string tricks);
- resource exhaustion (deep nesting, huge loops, huge output);
- injection into SMS and email headers;
- XSS in HTML output;
- cross-tenant data in the context.

## 6. Custom fields, forms, workflows, numbering

- **Custom fields:**
  - Only entities declared in a code registry accept custom fields. In Phase 5 these are `tenancy.institution`, `tenancy.campus`, `tenancy.member` and a test-only probe entity; Phase 6+ modules register theirs.
  - Values live in the entity's `extra` JSONB and are validated on every write against the active definition.
  - A field's type is never changed in place: the field is deprecated and a new one created.
  - Field-level permissions and PII masking apply.
  - Per-plan quotas apply.
- **Forms:** sections or steps of core and custom fields, with visibility rules evaluated in the rules sandbox. The DynamicForm renderer (frontend) builds the form from the server definition. The same validation runs server-side.
- **Workflows:** a declarative state machine.
  - Each transition carries a guard rule, a required permission and an approver resolution (role in scope or a specific member).
  - Actions on a transition are a domain event and a notification.
  - SLA and escalation timers use Celery beat.
  - Each instance pins its definition version.
- **Numbering sequences:**
  - Pattern tokens: `{INST}`, `{CAMPUS}`, `{YYYY}`, `{YY}`, `{AY}`, `{SEQ:n}`.
  - Gap-free counters are allocated under a row lock inside the business transaction, with a concurrency test.

## 7. Platform operations (catalogue additions)

| # | Operation | Actor | Mechanism |
|---|---|---|---|
| P21 | Preset catalogue sync | operator (owner-run bootstrap) | R (disabled as a runtime scope, like P20) |
| P22 | Apply a preset version to an institution at provisioning (inside P4) | user (`tenancy.tenant.create`) | T |
| P23 | Self-service sign-up (only if Q3 = yes) | anonymous, rate-limited | R + T |
| P24 | Workflow SLA and escalation sweep | system | I |

## 8. Permissions (new codes)

- `customization.config.view|edit|publish`
- `customization.field.view|manage`
- `customization.form.view|manage`
- `customization.rule.view|manage`
- `customization.workflow.view|manage`
- `customization.template.view|manage`
- `customization.numbering.view|manage`
- `notifications.notification.view_own`

`publish` and the rule, template and workflow `manage` codes require MFA. Publishing needs a fresh step-up. Role templates: `tenant_owner` and `institution_admin` get Studio codes in their scopes; other templates get none by default.

## 9. API and frontend

- **API (tenant host):**
  - `/customization/config/` (draft, publish, rollback, history, diff)
  - `/customization/fields/`, `/forms/`, `/rules/` (plus `/rules/{id}/test/`), `/workflows/`, `/templates/` (plus `/preview/`), `/numbering/`
  - `/me/context/` `terminology` filled from the resolver
  - `/notifications/`
- **API (platform host):** `/platform/presets/` (read).
- **OpenAPI and client:** 0 warnings; the TypeScript client is regenerated.
- **Frontend:**
  - the Studio area (mobile-first) with draft/preview/publish/rollback, a diff view and "test with sample data";
  - the DynamicForm renderer;
  - a notifications bell;
  - the onboarding wizard on first owner sign-in;
  - English and Bengali, with terminology loaded into the i18n messages.

## 10. Milestones

| M | Deliverable |
|---|---|
| M1 | `customization` app: `settings_schema` in manifests, config versions (draft/publish/rollback, diff, audit), effective config resolver and cache, permissions |
| M2 | Presets: repo files, owner-run sync (P21), six initial presets, preset pinning at provisioning (P22), capability flags, terminology in `/me/context/` |
| M3 | Rules sandbox (ADR-055) with namespaces, test cases and security tests; custom field definitions and the JSONB validation framework |
| M4 | Forms and the DynamicForm backend; workflow engine (definitions, instances, transitions, guards, approvers) and minimal `notifications_core`; SLA sweep (P24) |
| M5 | Template sandbox (ADR-056) with preview and security tests; numbering sequences with a concurrency test |
| M6 | APIs, OpenAPI and client |
| M7 | Frontend: Studio, DynamicForm renderer, notifications, onboarding wizard (and self-service sign-up if Q3 = yes), en + bn |
| M8 | E2E (a tenant per institution type from presets; publish/rollback), docs, security self-review, Phase 5 PR |

## 11. Proposed ADRs

- **ADR-055 (decides ADR-016):** an in-house, allow-listed JSONLogic-style evaluator, no new dependency, with limits and mandatory test cases per namespace.
- **ADR-056:** the template engine is Jinja2 `SandboxedEnvironment` (new dependency, justified: a purpose-built sandbox for untrusted templates) with plain-dict contexts, autoescape, allow-listed filters and limits. Alternative: a restricted Django template engine (no new dependency, but not designed as a sandbox).
- **ADR-057:** configuration storage: declared `settings_schema` keys, scoped config versions (draft/published/archived), resolution order, and a cache keyed by config version.
- **ADR-058:** presets are repo files (YAML, using the already-locked `pyyaml`, promoted to a direct dependency) synced by an owner-run bootstrap; institutions pin preset versions; upgrades are opt-in.
- **ADR-059:** minimal `notifications_core`: in-app notifications plus email through the existing mail path; SMS and push are Phase 14.

## 12. Questions for the owner

1. **Template engine:** Jinja2 sandbox (new dependency, purpose-built) or a restricted Django engine (no dependency)? **Recommendation:** Jinja2 `SandboxedEnvironment`.
2. **Rules evaluator:** in-house JSONLogic subset (small, fully audited, no dependency) or an external library? **Recommendation:** in-house.
3. **Self-service sign-up (ADR-054 Q1 placed it in Phase 5):**
   - Build it now, behind a feature flag that is **off by default**?
   - Abuse controls would be email verification, per-IP and per-email rate limits, a honeypot, pending sign-ups that expire after 48 hours, and an optional Super Admin approval step. There would be no external CAPTCHA (no accounts are created).
   - Tenant hosts stay disabled, so sign-ups are usable only after the production domain is approved.
   - **Recommendation:** yes, flag off by default.
4. **Preset content:** I draft the six presets (terminology en/bn, labels, capability flags, suggested modules) from the docs. Will you or real institutions review the content before Phase 6? **Recommendation:** ship as `v1` drafts and refine with feedback (new versions are opt-in).
5. **Quotas per plan** for Studio artefacts (custom fields per entity, forms, workflows, templates): add them as plan limit keys with platform defaults? **Recommendation:** yes. These limits are soft, warn first and then block new items, and are configurable per plan.

## 13. Implementation notes (appended during implementation)

### 13.1 M1 — configuration foundation (2026-11-22, branch `feat/phase-05-m1`)

| # | Note |
|---|---|
| C1 | New app `apps.customization` (platform module; moved from the planned catalogue to installed). Manifests may declare `SETTINGS` beside `PERMISSIONS`: key `<module>.<name>`, JSON Schema, a validating default, allowed scopes and a merge strategy (`replace`, or `deep` for objects). The catalogue is validated at load (bad keys, schemas, defaults, scopes or merges fail) |
| C2 | Declared keys so far: `customization.terminology` (per-locale overrides, deep merge, all scopes), `tenancy.week_start` (ISO 1–7, default 1) and `tenancy.academic_year_start_month` (1–12, default 1, tenant and institution). No country-specific defaults |
| C3 | `customization_configversion` (standard tenant RLS; composite `(tenant_id, …)` keys to institution and campus; reversal refused). Partial unique constraints: one draft and one published version per scope; version numbers unique per scope |
| C4 | Services: `save_draft` (full document of the scope), `discard_draft`, `publish` (archives the previous version), `rollback` (publishes a copy of an older version as a new version). Each checks the permission in the exact scope, uncached; validates declared keys, scope and schema (64 KiB maximum); serialises per scope with an advisory lock; and writes a tenant audit event with the changed key names (never values) |
| C5 | Resolver: defaults → preset layer (M2 hook `CUSTOMIZATION_PRESET_LAYER`) → tenant → institution → campus, published only. Keys removed from the catalogue are ignored. Cache per tenant and scope under a generation token replaced on publish, immediately and after commit |
| C6 | Permissions `customization.config.view|edit|publish` (edit: MFA; publish: MFA + step-up), 57 codes in total; `tenant_owner` holds them tenant-wide and `institution_admin` in their institution. `jsonschema` promoted from a transitive to a direct dependency (already locked; no stub package: two targeted `type: ignore` imports) |

### 13.2 M2 — presets (2026-11-22, branch `feat/phase-05-m2`)

| # | Note |
|---|---|
| C7 | Six v1 **draft** presets in `backend/apps/customization/presets/*.yaml` (ADR-060 Q4: to be validated with real institutions): `school.general.v1`, `college.general.v1`, `university.credit.v1`, `madrasa.general.v1`, `coaching.general.v1`, `training.general.v1`. Each holds en + bn terminology, structure levels, capability flags, role labels and suggested modules. Madrasa conventions are data, not code |
| C8 | New declared keys: `customization.capabilities` (flag → bool, deep merge, institution scope), `customization.structure_levels` (institution scope) and `customization.role_labels` (deep merge, tenant and institution). Code branches on capability flags, never on the institution type |
| C9 | Validation at load: code `<type>.<variant>.v<N>` of its type, version matching the code, known non-platform suggested modules, preset settings valid against the declared keys at institution scope, exactly one default per institution type, file named after its code |
| C10 | `customization_preset` (registry allow-list; SELECT only for the runtime role) written by the owner-run `sync_presets` (compose `migrate` step and test bootstrap; catalogue entry **P21**, disabled as a runtime scope). Synced presets are immutable (a changed file for an existing code is refused); removed presets are deprecated, never deleted. Audited (`customization.presets.synced`) |
| C11 | Pinning: new institutions (provisioning and the tenant-host create) store their type's default preset through the `TENANCY_INSTITUTION_PRESET` hook (tenancy does not import customization). No separate platform scope is needed (planned P22 runs inside the existing P4 / tenant transaction), so P22 is not added to the catalogue |
| C12 | Preset layer (`CUSTOMIZATION_PRESET_LAYER`): an institution scope inherits its pinned preset's settings below the tenant's own values; the tenant scope has no preset. `/me/context/` returns `terminology` (organisation) and `institution_terminology` (each active institution) |

### 13.3 M3 — rules sandbox and custom fields (2026-11-22, branch `feat/phase-05-m3`)

| # | Note |
|---|---|
| C13 | **Rules sandbox** (`apps/customization/rules.py`, ADR-055): JSON AST `{"op": [args]}`, 22 allow-listed operators (comparison, boolean, `if`, `+ - * /`, `min`/`max`, `round`, `in`, `var`, `missing`, `date`, `days_between`). Static check before evaluation: operators, namespace variables (exact or `prefix.*`), ≤ 500 nodes, ≤ 32 levels, strings ≤ 1,000 characters, lists ≤ 200 items. Evaluation: ≤ 10,000 steps, `Decimal` arithmetic (JSON numbers never stay floats), boolean-only conditions, `today` from the context (no clock), every error a `RuleError` |
| C14 | **Security tests** (exit criterion): code-execution and introspection payloads (`__import__`, `eval`, `exec`, `getattr`, `__class__`, `lambda`, `map`, `reduce`), variables outside the namespace, malformed operations, nesting/size/step limits, arithmetic and type errors, result types, determinism |
| C15 | **Namespaces** are declared in manifests (`RULE_NAMESPACES`): `customization.form_visibility` and `customization.workflow_guard` (boolean). Later modules add theirs (e.g. `fees.late_fine`) |
| C16 | `customization_ruledefinition` (standard RLS): versioned per key, one draft and one published version; saving checks the rule; publishing needs `customization.config.publish`, at least one test case and all cases passing; the namespace of a key never changes. `evaluate_published()` is the entry point for forms and workflows |
| C17 | **Custom fields:** entities declared in manifests (`CUSTOM_FIELD_ENTITIES`: `tenancy.institution`, `tenancy.campus`, `tenancy.member`). `customization_fielddefinition` (standard RLS): ten types, i18n labels, options for choice fields, per-type limits, visibility, view/edit permissions (must exist), PII flag, order. Key and type never change (deprecate and create). `validate_values()` refuses unknown and deprecated keys, enforces required fields and fixed per-type schemas (decimals as strings, real calendar dates, ranges) |
| C18 | Permissions `customization.rule.view|manage`, `customization.field.view|manage` (manage: MFA), 61 codes in total; tenant owners hold them. **Not yet built:** storing values on the tenancy entities (`extra` columns, wired with the APIs in M6) and per-plan Studio quotas (ADR-060 Q5; planned with the APIs in M6). A test found and fixed a missing check: a choice field could be created without options |

### Change notes
- 2026-11-22 — Created (Proposed).
- 2026-11-22 — Approved by the owner with the recommended answers (ADR-060); ADR-055 to ADR-059 Accepted.
- 2026-11-22 — §13.1 appended: M1 notes C1–C6.
- 2026-11-22 — §13.2 appended: M2 notes C7–C12.
- 2026-11-22 — §13.3 appended: M3 notes C13–C18.
