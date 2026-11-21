# CLAUDE.md — Permanent Project Instructions

> **This file is the permanent, authoritative instruction source for every Claude Code session on this repository.**
> Read it completely before doing any work. If anything in another document conflicts with this file, this file wins
> until the conflict is resolved and recorded in `docs/DECISION_LOG.md`.

- **Project:** Education ERP — Global Multi-Tenant Configurable Education Management SaaS
- **Repository:** `shafikcmt/education-erp-platform`
- **Document owner:** Project owner (approval authority). Claude acts as Principal Software Architect, Technical Project Manager and Lead Full-Stack Engineer.
- **Last updated:** 2026-11-21 (Phase 3 **Complete**: M1–M11 merged (PRs #17, #18, #29–#36, #41, #42); D9 benchmark moved to Phase 18 (ADR-049); tenant hosts disabled; awaiting owner approval; Phase 4 plan proposed, not started)

---

## 0. Mandatory Session Protocol (read first, every session)

1. Read this `CLAUDE.md` fully.
2. Read `docs/DEVELOPMENT_PROGRESS.md` to learn the current phase, status and open items.
3. Read `docs/DECISION_LOG.md` — only **Accepted** decisions may be implemented. **Proposed** decisions must not be built on until approved (except where explicitly noted as a safe default).
4. Read the documents relevant to the task (see the index in §19).
5. Inspect the existing code before changing it. Never assume a feature exists — verify in code.
6. Work only on the phase that is currently approved. **Never start the next major phase without the owner's explicit approval.**
7. Never overwrite or delete user-created reports or documents. Append, amend with clear change notes, or create a new file.
8. Never mark a feature complete unless it is implemented, tested, linted, type-checked and documented. Partial work is recorded as *In progress* or *Partial* with what is missing.
9. Never silently skip a requirement. If a requirement cannot be met, say so and record it in `DEVELOPMENT_PROGRESS.md` (“Known gaps”).
10. End every session with: summary of changes, test/lint results (actual output, not assumptions), updated progress file, open questions, and a recommended next task.

---

## 1. Project Vision and Business Goals

Build a **single, global, multi-tenant, configurable SaaS** that lets any education institution — from a small coaching center to a multi-campus university group or a residential madrasa — run its entire operation (admissions, academics, attendance, examinations, fees, accounting, HR, hostel, transport, library, LMS, communication, analytics and AI assistance) **from one codebase**, configured rather than forked.

Business goals:

1. **One product, many institution types.** Serve School, College, University, Madrasa, Coaching Center and Training Institute through configuration, not separate code.
2. **Recurring revenue** via subscription plans, paid add-on modules, usage-based extras (SMS, storage, AI) and enterprise contracts.
3. **Fast onboarding** — an institution should be able to self-onboard with an institution-type preset and be usable the same day.
4. **Trust** — strict tenant isolation, audited access, financial correctness and reliable backups are non-negotiable selling points.
5. **Global readiness** — multi-language (incl. RTL), multi-currency, multi-timezone, configurable academic calendars and grading systems. Bangladesh is a priority early market (Bengali UI, local payment gateways, local exam/grading conventions), but nothing may be hardcoded to one country.
6. **Mobile-first, premium UX** — most parents, students and many teachers use phones.
7. **Cost efficiency** — a modular monolith on commodity infrastructure (Docker, PostgreSQL, Redis) keeps hosting cost per tenant low.

Details: `docs/PROJECT_VISION.md`.

---

## 2. Global Multi-Tenant SaaS Requirements

- **Tenant** = a paying customer organization (one contract, one subscription). A tenant owns one or more **Institutions**; each institution has one or more **Campuses** (branches).
  `Platform → Tenant → Institution → Campus`
- All tenants run on the **same codebase and same deployment** (shared infrastructure). Enterprise tenants may later receive dedicated database/infrastructure *using the same code* (see ADR-009).
- Tenant resolution: subdomain (`{tenant}.<platform-domain>`) or verified custom domain → server resolves tenant; the client never decides tenant scope by itself.
- Per-tenant settings: locale(s), timezone, currency, academic calendar, branding (logo, colors), terminology, numbering formats.
- Data residency, export (tenant data portability) and deletion (offboarding) must be supported.
- Self-service onboarding wizard + Super Admin-assisted onboarding.
- **Subscription is owned at tenant level** (one subscription per tenant). Institution and campus counts are limited by configurable plan limits (`max_institutions`, `max_campuses`) with audited Super Admin overrides (ADR-010, accepted).
- Usage limits per plan (students, institutions, campuses, storage, SMS credits, AI usage) enforced server-side.

Details: `docs/MULTI_TENANT_ARCHITECTURE.md`, `docs/REQUIREMENTS.md`.

---

## 3. Supported Institution Types

| Code | Institution type | Typical structure (preset) |
|---|---|---|
| `school` | School (primary/secondary/high) | Academic Year → Class/Grade → Section → Subject |
| `college` | College (higher secondary/degree) | Academic Session → Group/Stream → Year/Class → Section → Subject |
| `university` | University | Faculty → Department → Program → Semester/Term → Course (credit-based), CGPA |
| `madrasa` | Madrasa (Qawmi/Alia/Hifz, configurable) | Session → Marhala/Level → Jamaat/Class → Kitab/Subject; Hifz progress; residential hostel |
| `coaching_center` | Coaching Center | Program/Course → Batch → Session/Class; model tests |
| `training_institute` | Training Institute | Course → Batch/Cohort → Module; certificates |

The institution type selects a **preset (configuration pack)**; it never selects a different codebase. A tenant may run institutions of different types.

---

## 4. Three Customization Levels

| Level | Name | Who changes it | Mechanism |
|---|---|---|---|
| **L1** | Standard shared ERP modules | Platform engineering only | Core code in the monorepo; same for all tenants |
| **L2** | Institution-type-specific configuration | Platform (presets), versioned | Configuration packs per institution type: terminology, academic structure templates, grading presets, default roles, default modules, report templates |
| **L3** | Tenant-specific custom extensions | Tenant admins via Customization Studio (or platform team for enterprise) | Custom fields, forms, workflows, rules, templates, terminology overrides, custom reports, custom entities (Phase 17) — **declarative, versioned, data-driven** |

**Rules:**
- Never create separate codebases, branches or forks per institution or tenant.
- Never put `if tenant == "X"` logic in code. Tenant differences are expressed in configuration or entitlements.
- Institution-type differences are expressed through presets and capability flags (e.g. `academics.credit_based`), not `if institution_type == ...` scattered across code. Where code must branch, branch on a **capability flag**, centrally.
- L3 extensions are **declarative only** (no tenant-supplied executable code). Rules use a safe expression format (see ADR-016).
- Configuration resolution order (later overrides earlier): **Core defaults → Institution-type preset → Tenant → Institution → Campus**.
- All configuration is **versioned** (draft → published → archived) with rollback and audit.

Details: `docs/CUSTOMIZATION_ENGINE.md`.

---

## 5. Module List and Responsibilities

Module codes are canonical identifiers used in code, entitlements, permissions and docs.

**Platform modules (always on, not sold separately):**

| Code | Responsibility |
|---|---|
| `core` | Base models, tenant context primitives, error format, pagination, money utilities, domain event bus, health endpoints |
| `tenancy` | Tenants, institutions, campuses, domains, tenant settings, onboarding/offboarding |
| `identity` | Users, authentication, MFA, sessions, password policy, invitations |
| `rbac` | Roles, permissions, role assignments with scopes |
| `module_registry` | Module manifests, versions, dependencies, entitlement resolution, feature flags |
| `billing` | SaaS plans, subscriptions, add-ons, usage metering, SaaS invoices (platform ↔ tenant) |
| `customization` | Customization Studio backend: custom fields, forms, workflows, rules, templates, terminology |
| `audit` | Append-only audit log, data access log, support-access log |
| `files` | File storage abstraction (S3-compatible API; SeaweedFS in dev — ADR-029), presigned URLs, virus-scan hook, quotas |
| `notifications_core` | Notification dispatch infrastructure used by all modules |

**Standard ERP modules (entitled by plan or add-on):**

| Code | Responsibility |
|---|---|
| `academics` | Academic years/sessions, terms/semesters, programs, classes/grades, sections, subjects/courses, curriculum, promotion rules |
| `timetable` | Periods, rooms, class/teacher timetables, substitutions |
| `admissions` | Inquiries, online applications, admission tests, merit lists, enrollment |
| `students` | Student profiles, guardians, documents, enrollment history, promotion/transfer, ID cards, alumni status |
| `staff` | Teacher/staff profiles, departments, designations, assignments |
| `parent_portal` | Parent/guardian portal and student self-service views |
| `attendance` | Student and staff attendance (daily/period/session), leave, device integrations |
| `examinations` | Exam setup, grading schemes, marks entry, moderation, results, report cards, transcripts, GPA/CGPA |
| `fees` | Fee heads/structures, invoices, discounts/scholarships/waivers, collections, online payments, dues, receipts |
| `accounting` | Chart of accounts, double-entry journal, vouchers, ledgers, bank reconciliation, financial statements. The ledger *posting engine* is always installed so fees always post balanced entries; the `accounting` entitlement unlocks GL features (proposed ADR-025) |
| `hr_payroll` | Leave, salary structures, payroll runs, payslips, advances/loans, statutory deductions |
| `hostel` | Custom Hostel Engine (see §7) |
| `transport` | Vehicles, routes, stops, assignments, transport fees |
| `library` | Catalog, copies, circulation, reservations, fines |
| `lms` | Course content, assignments, submissions, online class links |
| `online_exams` | Question banks, online tests, auto-grading, result publishing |
| `communication` | Notices, SMS, email, push, in-app messages, templates, delivery logs |
| `reports_analytics` | Standard reports, dashboards, custom report builder, exports |
| `ai_assistant` | Permission-aware AI assistant (see §13) |
| `custom_module_builder` | Tenant-defined entities/screens (Phase 17, enterprise) |

**Institution-type extension modules (L2, optional):** e.g. `ext_hifz_tracking` (madrasa), `ext_course_registration` (university credit registration), `ext_batch_management` (coaching), `ext_certification` (training institute). Full list and dependencies: `docs/MODULE_CATALOG.md`.

**Module boundaries:** each module is a Django app (or group of apps) with its own models, services, API, permissions, tests and manifest. Modules talk to each other through **service-layer functions and domain events**, never by reaching into another module's internals or tables directly.

---

## 6. Customization Studio Requirements

A no-code admin area (Phase 5, extended in Phase 17) where authorized tenant admins can:

1. Choose/adjust institution-type preset and terminology (e.g. “Class” → “Grade”, “Section” → “Jamaat”).
2. Define **custom fields** on supported entities (student, guardian, staff, application, invoice, hostel allocation, …) with type, validation, visibility and permission.
3. Build **forms** (admission form, inquiry form, leave form) from core + custom fields.
4. Configure **workflows/approvals** (e.g. admission approval chain, leave approval, fee waiver approval) as declarative state machines.
5. Configure **rules** (fee late-fine rules, promotion rules, grading rules, attendance thresholds) via safe expressions.
6. Design **templates** (report card, admit card, ID card, certificate, receipt, SMS/email) with a sandboxed template language.
7. Configure **numbering sequences** (student ID, invoice no., receipt no.).
8. Configure **dashboards and report layouts**.
9. Preview → publish → rollback configuration versions; see a change history.

Every Studio artefact is tenant-scoped, versioned, validated server-side, permission-protected (`customization.*` permissions) and audited. Details: `docs/CUSTOMIZATION_ENGINE.md`.

---

## 7. Custom Hostel Engine (Madrasa + University)

The `hostel` module is a **configurable engine**, not two hardcoded hostels.

- Generic model: `Hostel → Building/Block → Floor → Room → Bed`, room types, capacities, gender/eligibility policies, facilities.
- **Hostel profiles** (L2 presets) configure behavior:
  - **Madrasa residential profile:** boarding is often mandatory/common; strict gender segregation; age/level-based allocation; guardian visit schedules; leave/out-pass with guardian authorization; daily roll-calls (multiple per day, configurable); curfew; meal/mess plans; study-hour supervision; warden/superintendent (e.g. *Nazim*) roles; monthly boarding fees.
  - **University profile:** hall/residence applications; seat allocation by merit/criteria/lottery; semester- or year-based tenure; room change requests; provost/house-tutor roles; hall fees per semester; check-in/check-out; visitor logs.
- Configurable via Studio: allocation policy (manual / rule-based / merit), roll-call schedule, leave workflow, meal plans, fee plans (linked to `fees`), visitor rules, disciplinary incident types.
- Integrations: `fees` (hostel charges, mess bills), `attendance` (roll-call), `students`, `communication` (guardian alerts), `reports_analytics`.

Details: `docs/MODULE_CATALOG.md#hostel`, `docs/CUSTOMIZATION_ENGINE.md#hostel-profiles`.

---

## 8. Subscription Plans, Paid Modules and Enterprise Pricing

- Plan codes: `trial`, `starter`, `growth`, `professional`, `enterprise`.
- Each plan defines: included modules, usage limits (active students, campuses, staff users, storage, SMS credits, AI quota), support level.
- **Paid add-on modules** can be attached to any non-enterprise plan where dependencies allow (e.g. `hostel`, `transport`, `lms`, `online_exams`, `ai_assistant`, `hr_payroll`, `accounting`).
- **Enterprise:** custom contract, custom limits, custom extensions, SSO, dedicated infrastructure option, SLA, priced by quotation.
- Pricing metric (proposed, ADR-024): tiered by active students + add-ons + usage. **Actual price numbers are NOT decided** — they require market research and owner approval. Never invent prices in code; prices live in data (Plan/Price tables), never constants.
- Entitlements are enforced **server-side** on every request (module enabled + within limits). The UI only hides what the server already forbids.
- SaaS billing (platform ↔ tenant) is separate from the tenant's own student-fee collection (`fees`).

Details: `docs/SUBSCRIPTION_AND_BILLING.md`.

---

## 9. Users and Roles

**Platform-level roles** (no tenant membership by default; **no implicit tenant-data access**: support access only via audited, time-limited support sessions, Phase 3):
- `super_admin` — full platform administration (tenants, plans, modules, global config). MFA mandatory.
- `platform_support` — read-only tenant diagnostics; tenant data access **only** via time-bound, reason-logged, audited support sessions (optionally requiring tenant consent).
- `platform_billing` — plans, subscriptions, invoices; no tenant academic data.
- `platform_onboarding` — create/configure new tenants during onboarding.

**Institution-level (tenant) role templates** (tenants may clone and customize):
`tenant_owner`, `institution_admin` (Principal/Head/Rector/Muhtamim), `campus_admin`, `academic_coordinator` (incl. Head of Department), `teacher`, `class_teacher` (advisor), `exam_controller`, `admission_officer`, `accountant`, `cashier`, `hr_manager`, `librarian`, `hostel_warden`, `transport_manager`, `front_desk`, `staff_member` (generic non-teaching staff), `student`, `guardian`.

- Roles are **bundles of permissions**; authorization checks **permissions**, never role names.
- A user may hold different roles in different institutions/campuses (scoped role assignments). One person (e.g. teacher who is also a parent) uses one account.

Details: `docs/SECURITY.md#rbac`.

---

## 10. Strict Tenant Isolation and RBAC

**Tenant isolation (non-negotiable):**
1. Every tenant-owned table has a non-null `tenant_id` and inherits the shared `TenantScopedModel` base.
2. The tenant context is resolved **server-side** per request (domain + authenticated membership). Client-supplied tenant IDs are never trusted on their own.
3. All tenant-owned queries go through a tenant-aware manager that **fails closed** (raises) when no tenant context is set. Unscoped access is only possible through an explicit, audited `platform_scope()` context used by platform code, through the platform operation catalogue (registry, targeted tenant transaction, per-tenant iteration, reviewed `SECURITY DEFINER` functions). There is **no runtime `BYPASSRLS`**: `erp_platform` stays `NOLOGIN` and unused, and any break-glass access needs a new ADR (ADR-043, amending ADR-009 §5).
4. Defense-in-depth: PostgreSQL **Row-Level Security** (`ENABLE` + `FORCE`) on every tenant table, with a policy keyed on the **transaction-scoped** setting `app.tenant_id`. If the setting is unset, no rows are visible (fail closed). Accepted in ADR-009.
   - The tenant is set with `set_config('app.tenant_id', …, true)` at the start of **every** tenant transaction, through the single helper `core.db.tenant_atomic(tenant)`. Session-level `SET` is forbidden.
   - The runtime DB role `erp_app` is non-superuser, non-owner and `NOBYPASSRLS`. Migrations run as `erp_owner`. Tests also run as `erp_app`.
5. Celery tasks carry `tenant_id` explicitly and re-establish tenant context; no task runs tenant code without it.
6. Files are stored under tenant-prefixed keys and served only through authorized presigned URLs.
7. Caches keys are tenant-prefixed. Search indexes and AI embeddings are tenant-filtered.
8. Every module ships **cross-tenant isolation tests** (tenant A must never read/write tenant B). A failing isolation test blocks merge.

**Authorization pipeline (every API request, every AI tool call, every custom module action):**
`Authenticate → Resolve tenant → Verify membership → Check module entitlement → Check permission → Check scope (institution/campus/own-records) → Field-level masking → Audit`

- Permission code format: `<module>.<resource>.<action>` (e.g. `students.student.view`, `fees.payment.refund`).
- Default deny. Permissions are checked in DRF permission classes and service-layer functions (both), not only in the UI.
- **AI assistant and custom modules never bypass authorization** — they execute as the requesting user with the same pipeline.

Details: `docs/MULTI_TENANT_ARCHITECTURE.md`, `docs/SECURITY.md`.

---

## 11. Database Architecture

- **PostgreSQL 17** is the only primary datastore. Use JSONB for flexible/custom data and **pgvector** for AI embeddings.
- **MongoDB (or any other primary DB) must not be introduced** without a documented technical justification accepted in `DECISION_LOG.md`.
- Tenancy model (ADR-009, accepted): shared database, shared schema, `tenant_id` column on all tenant data + RLS with transaction-scoped tenant context.
- Base model conventions: UUIDv7 primary keys (ADR-012, accepted) generated only via `core.ids.new_id()` (pinned library behind one abstraction; no direct library imports), `tenant_id`, `created_at`, `updated_at`, `created_by`, `updated_by`; soft-archive for master data; **financial records are immutable** (corrections by reversal entries).
- Money: `NUMERIC(18,2)` (Django `DecimalField`) + ISO-4217 currency code. **Never use floats for money.**
- All financial operations run inside `transaction.atomic()` with row locking (`select_for_update`) where balances change, and idempotency keys for payment endpoints.
- Custom field values: `extra JSONB` column validated against tenant field definitions; GIN-indexed where queried.
- Migrations: reviewed in every PR; must be backward compatible (expand → migrate → contract) for zero-downtime deploys; no data-destroying migration without explicit approval.
- Key relationships: Tenant 1–N Institution 1–N Campus; User N–N Tenant via Membership; Membership 1–N RoleAssignment (scoped); Student N–N Guardian; Student 1–N Enrollment (per academic year/class/section); etc.

Details: `docs/DATABASE_DESIGN.md`, `docs/ERD.md`.

---

## 12. API and Frontend Architecture

**API (Django REST Framework):**
- **Authentication (ADR-011, accepted with modification):**
  - The first-party browser app uses **Django session authentication**: HttpOnly + Secure + SameSite=Lax host-only session cookie, CSRF protection on all unsafe methods, and same-origin web + API behind Nginx.
  - Next.js never holds or mints credentials. **No tokens in localStorage/sessionStorage, ever.**
  - Mobile apps and third-party APIs will use a separate OAuth/JWT-compatible token path (mechanism: ADR-028, proposed) that goes through the same authorization pipeline.
- REST, versioned under `/api/v1/`. OpenAPI 3 schema generated by `drf-spectacular`; TypeScript client/types generated from it for the frontend.
- Layering inside each module: `models → selectors (reads) → services (writes/business logic, transactions) → serializers → views/viewsets → urls`. Business logic lives in services, **not** in views or serializers.
- Standard errors (RFC 9457 Problem Details style), cursor/page pagination, filtering, ordering, `Idempotency-Key` for payment/money endpoints, rate limiting, request IDs.
- Details: `docs/API_STANDARDS.md`.

**Frontend (Next.js 16, App Router, TypeScript strict, Tailwind CSS, shadcn/ui):**
- Mobile-first, accessible (WCAG 2.2 AA target), i18n (English + Bengali initially; Arabic RTL ready), tenant theming via CSS variables.
- Server state via TanStack Query; forms via react-hook-form + zod; generated API types — no hand-written duplicate types.
- UI renders modules dynamically from the server-provided **entitlement + permission manifest**; hidden ≠ secure — the server enforces.
- Details: `docs/FRONTEND_STANDARDS.md`.

---

## 13. AI Assistant Architecture

- `ai_assistant` is a paid module. It is an **orchestrator** that calls an LLM provider through a provider-abstraction layer (default proposed: Anthropic Claude; model IDs are configuration, never hardcoded).
- **Tools, not raw database access:** the AI can only act through registered tools that call the same service/selector layer, under the requesting user's identity, tenant and permissions (full authorization pipeline). No tool may run raw SQL.
- **RAG:** tenant-scoped documents (policies, notices, help docs) embedded into pgvector with `tenant_id` + permission metadata; retrieval is filtered by tenant and the user's access.
- Write actions proposed by AI require explicit user confirmation; financial writes by AI are disabled by default.
- PII minimization, prompt-injection defenses, per-tenant opt-in, usage quotas, full audit of prompts/tool calls (with retention policy).

Details: `docs/AI_ASSISTANT.md`.

---

## 14. Security, Testing, Backup and Monitoring Standards

**Security:** OWASP ASVS L2 target; Argon2 password hashing; MFA mandatory for **privileged accounts** (data-driven: any permission flagged `requires_mfa`; ADR-035), optional for ordinary users; step-up re-authentication for sensitive operations; no user enumeration; encrypted security-event IPs (ADR-036); secure cookies; CSRF protection; strict CORS; CSP; rate limiting; input validation; output encoding; dependency and secret scanning in CI; secrets only via environment/secret manager — **never commit secrets**; least-privilege DB roles; encrypted backups; audit logging; PII handling and data retention policies. Details: `docs/SECURITY.md`.

**Testing:** pytest + pytest-django + factory_boy (backend); Vitest + Testing Library (frontend); Playwright (E2E). Mandatory per module: unit tests for services, API tests for permissions (allowed + denied), **tenant isolation tests**, and transaction/concurrency tests for financial code. Coverage target ≥ 85% for backend services. Details: `docs/TESTING_STRATEGY.md`.

**Backup:** automated PostgreSQL base backups + WAL archiving for point-in-time recovery, encrypted, off-site; object storage versioning; documented and **periodically tested restore**; per-tenant export. Targets (proposed): RPO ≤ 15 min, RTO ≤ 4 h.

**Monitoring:** Sentry (backend + frontend), structured JSON logs (structlog) with `request_id`, `tenant_id`, `user_id`; health/readiness endpoints; Celery queue monitoring; uptime checks; alerting.

---

## 15. Docker Deployment and CI/CD

- Every service runs in Docker. `docker compose` for local development; production uses hardened images and a production compose (or orchestrator later).
- Services: `nginx`, `web` (Next.js), `api` (Django/Gunicorn+Uvicorn workers), `worker` (Celery), `beat` (Celery beat), `postgres` (17 + pgvector), `redis`, `objectstore` (S3-compatible dev/self-hosted storage — SeaweedFS, ADR-029), plus one-shot `migrate` (runs as `erp_owner`) and `objectstore-init`, and `mailpit` (dev email). Image versions are pinned (ADR-030).
- Multi-stage builds, non-root users, pinned base images, health checks, no secrets in images.
- **GitHub Actions:** on every PR — lint (ruff, ESLint), format check, type check (mypy, tsc), tests (with Postgres+Redis services), migration check, OpenAPI drift check, security scans, Docker build. On merge to `main` — build & push images, deploy to staging. Production deploy — tagged release + manual approval.
- Details: `docs/DOCKER_DEPLOYMENT.md`.

---

## 16. Coding Standards and GitHub Workflow

**Repository layout (monorepo, ADR-014, accepted):**
```
/CLAUDE.md                 permanent instructions (this file)
/README.md
/docs/                     all project documentation
/backend/                  Django project (Python 3.13, Django 5.2 LTS, DRF)
  config/                  settings (base/dev/test/prod), urls, celery, asgi/wsgi
  apps/<module>/           one Django app per module (models, selectors, services, api, permissions, manifest, tests)
/frontend/                 Next.js 16 app (TypeScript, Tailwind, shadcn/ui)
/packages/api-client/      generated TypeScript types/client from OpenAPI
/infra/                    docker, nginx, scripts
/.github/                  workflows/ (CI/CD), dependabot.yml, pull_request_template.md
/docker-compose.yml, /.env.example, /Makefile, /package.json, /pnpm-workspace.yaml   root tooling
```

**Python:** ruff (lint+format), mypy with django-stubs (strict on new code), type hints everywhere, services are plain functions with explicit arguments (`tenant`, `actor`), no business logic in views/serializers/signals, no N+1 queries (use `select_related`/`prefetch_related`), dependencies managed with `uv` (`pyproject.toml` + committed `uv.lock`, `uv sync --frozen` in CI/Docker; ADR-013, accepted).

**TypeScript:** `strict: true`, ESLint + Prettier, no `any` without justification, server components by default, client components only when interactive, `pnpm` workspace at repo root with committed `pnpm-lock.yaml`, `--frozen-lockfile` in CI/Docker (ADR-013, accepted).

**General:** small focused changes; no duplicated code — extract shared utilities; no unnecessary dependencies (each new dependency justified in the PR); meaningful names; comments explain *why*; feature flags for unfinished features; i18n for every user-facing string.

**GitHub workflow:**
- **Never commit directly to `main`** unless the owner explicitly authorizes it.
- Feature branches: `feat/<phase>-<short-name>`, `fix/...`, `docs/...`, `chore/...` (or the session-assigned branch).
- Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- Pull requests for every change, with: summary, phase, affected modules, migrations, security implications, tests run (with results), docs updated.
- Every PR touching models must have its migrations reviewed; every PR touching auth/tenancy/finance gets an explicit security review note.
- Never expose secrets, credentials, production data or personal data in code, issues, PRs, logs or docs.

---

## 17. Step-by-Step Development Sequence

| Phase | Scope |
|---|---|
| 0 | Documentation and architecture baseline (approved; merged in PR #1) |
| 1 | Repository foundation and infrastructure (approved 2026-11-06) |
| 2 | Authentication, users, roles and permissions (approved; merged in PR #15) |
| 3 | SaaS tenants, institutions and campuses (plan `docs/plans/PHASE_03_PLAN.md` rev. 3 **Approved**; ADR-041–049 Accepted; **Complete**: M1–M11 merged in PRs #17, #18, #29–#36, #41, #42; D9 benchmark moved to Phase 18 (ADR-049); awaiting the owner's approval of the phase) |
| 4 | Module registry and feature entitlement engine (plan `docs/plans/PHASE_04_PLAN.md` **Proposed**; ADR-050–053 Proposed; not started) |
| 5 | Customization Studio and institution configuration |
| 6 | Academic structure and student admission |
| 7 | Student, teacher and parent management |
| 8 | Attendance management |
| 9 | Examination and results |
| 10 | Fees and financial accounting |
| 11 | HR and payroll |
| 12 | Hostel, transport and library |
| 13 | LMS and online examinations |
| 14 | Notifications and communication |
| 15 | Reports and analytics |
| 16 | AI assistant |
| 17 | Institution-specific extensions and custom module builder |
| 18 | Security, performance and production readiness |
| 19 | Docker production deployment and CI/CD |

> Note: Phase 2 builds the RBAC engine; tenant-scoped role assignment is completed once Phase 3 introduces tenants. Basic Docker Compose and CI (lint/test) start in Phase 1; Phase 19 is *production* hardening of deployment and CD.

**Per-phase procedure (mandatory):**
1. Read `CLAUDE.md`. 2. Review relevant docs and code. 3. Check dependencies/prerequisites (previous phase approved and complete). 4. Write a detailed implementation plan (and share it). 5. Identify affected models and migrations. 6. Implement backend APIs. 7. Implement frontend interfaces. 8. Add tenant isolation and permission checks. 9. Add automated tests. 10. Run tests, linting and type checking. 11. Fix all errors before declaring completion. 12. Update `docs/DEVELOPMENT_PROGRESS.md`. 13. Update relevant documentation (and `DECISION_LOG.md` for any decision). 14. Provide a summary and **wait for owner approval before the next major phase**.

Details, deliverables and exit criteria: `docs/DEVELOPMENT_ROADMAP.md`.

---

## 18. Rules for Updating Documentation and Tracking Progress

1. `docs/DEVELOPMENT_PROGRESS.md` is updated at the end of every working session: phase status, completed items (with PR links), in-progress items, known gaps, test status, next task.
2. Status vocabulary (use exactly): `Not started`, `Planned`, `In progress`, `Partial`, `Blocked`, `Complete`, `Approved`. A phase is `Complete` only when all exit criteria pass; `Approved` only after the owner approves.
3. Every architectural/technical decision goes into `docs/DECISION_LOG.md` as an ADR entry with status `Proposed`, `Accepted`, `Superseded` or `Rejected`. Accepted decisions are changed only by a new ADR that supersedes them.
4. When requirements or decisions change, update **this file and all affected docs in the same PR**, and add a change note at the bottom of each changed document.
5. Never delete history from the progress or decision logs; append.
6. Docs must describe what **is**, plus clearly labelled plans. Do not document unimplemented features as implemented.
7. Keep terminology and codes (module codes, plan codes, role codes, permission format, phase numbers) consistent with this file.

---

## 19. Documentation Index

| Document | Purpose |
|---|---|
| `README.md` | Project overview and quick start |
| `docs/PROJECT_VISION.md` | Vision, goals, market, personas, success metrics |
| `docs/REQUIREMENTS.md` | Functional and non-functional requirements |
| `docs/SYSTEM_ARCHITECTURE.md` | Overall architecture, layers, components, flows |
| `docs/TECH_STACK.md` | Technologies, versions, justification |
| `docs/DATABASE_DESIGN.md` | Data model conventions, schemas per module |
| `docs/ERD.md` | Entity-relationship diagrams (Mermaid) |
| `docs/MULTI_TENANT_ARCHITECTURE.md` | Tenancy model, isolation, resolution |
| `docs/MODULE_CATALOG.md` | Every module: responsibilities, dependencies, permissions |
| `docs/CUSTOMIZATION_ENGINE.md` | L1/L2/L3 customization, Studio, presets, hostel profiles |
| `docs/SUBSCRIPTION_AND_BILLING.md` | Plans, add-ons, entitlements, metering, SaaS billing |
| `docs/SECURITY.md` | Security standards, RBAC, data protection |
| `docs/API_STANDARDS.md` | REST conventions |
| `docs/FRONTEND_STANDARDS.md` | Frontend conventions |
| `docs/AI_ASSISTANT.md` | AI assistant architecture and safety |
| `docs/DOCKER_DEPLOYMENT.md` | Containers, environments, CI/CD |
| `docs/TESTING_STRATEGY.md` | Test pyramid, mandatory tests, quality gates |
| `docs/DEVELOPMENT_ROADMAP.md` | Phases, deliverables, exit criteria |
| `docs/DEVELOPMENT_PROGRESS.md` | Live progress tracker |
| `docs/DECISION_LOG.md` | Architecture Decision Records |
| `docs/plans/PHASE_XX_PLAN.md` | Per-phase implementation plans (status Proposed → Approved) |

---

## 20. Absolute Rules (quick reference)

- One codebase. No per-institution forks. No `if tenant == ...`.
- Modular monolith first; extract services only with an accepted ADR and measured need.
- Server-side tenant isolation everywhere; fail closed.
- Permissions checked server-side on every action, including AI and custom modules.
- Money: Decimal + currency, atomic transactions, immutable ledgers, idempotency.
- PostgreSQL only (JSONB, pgvector); no MongoDB without accepted ADR.
- No secrets in the repo. No production data in dev/test.
- No new dependency without justification. No duplicated code.
- Tests + lint + type checks pass before "done". Report real results.
- Update progress and docs every session. Wait for approval between phases.

---

### Change notes
- 2026-11-05 — Initial version created (Phase 0).
- 2026-11-05 — Owner approved ADR-009, ADR-010, ADR-012, ADR-013, ADR-014 and ADR-011 (with modification: Django session auth). Updated §2, §10, §11, §12, §16 accordingly. ADR-028 added (Proposed).
- 2026-11-05 — Phase 1: ADR-015/021 accepted; storage service renamed to `objectstore` (SeaweedFS, ADR-029); phase table updated.
- 2026-11-05 — Phase 1 review: ADR-029 (SeaweedFS, conditions verified) and ADR-030 (TS 5.9 / ESLint 9 held temporarily) accepted.
- 2026-11-05 — Phase 2 approvals (ADR-031 to ADR-037): `staff_member` role code; privileged-account MFA + step-up; IP privacy; platform roles have no implicit tenant-data access.
- 2026-11-06 — Phase 1 approved; Phase 2 plan approved and implemented (PR #15). Phase table updated; no rule changed.
- 2026-11-08 — Phase 2 approved and merged (PR #15); Phase 3 plan and ADR-041 to ADR-046 proposed. Phase table updated; no rule changed (ADR-043 would amend ADR-009 §5 and this file's §10 wording on `platform_scope()` only if accepted).
- 2026-11-08 — Phase 3 plan rev. 2: the phase table and last-updated line were updated. No rule changed. On acceptance, ADR-043 adds wording to §10 item 3 (platform operation catalogue, no runtime `BYPASSRLS`). ADR-047 records the owner's answers to Q1–Q12.
- 2026-11-08 — Phase 3 plan rev. 3: the phase table and last-updated line were updated. No rule changed. The §10 wording change from ADR-043 is still applied only on final acceptance.
- 2026-11-08 — Owner final approval of the Phase 3 plan: ADR-041–047 Accepted. §10 item 3 now states the platform operation catalogue and no runtime `BYPASSRLS` (ADR-043 amends ADR-009 §5). Phase table updated.
- 2026-11-09 — Phase 3 M1 (incl. O1) complete; phase table and last-updated line updated. No rule changed.
- 2026-11-09 — Phase 3 M1 merged; M2 complete on its branch; phase table and last-updated line updated. No rule changed.
- 2026-11-09 — Phase 3 M2 merged (PR #18, `3616778`); phase table and last-updated line updated. No rule changed.
- 2026-11-13 — Phase 3 M3 complete on its branch (ADR-048 records the owner's M3 decisions); phase table and last-updated line updated. No rule changed.
- 2026-11-16 — Phase 3 M4 complete on its branch; phase table and last-updated line updated. No rule changed.
- 2026-11-17 — Phase 3 M3 merged (PR #29, `066b727`); phase table and last-updated line updated. No rule changed.
- 2026-11-18 — Phase 3 M4 merged (PR #30, `14a54d6`); M5 complete on its branch; phase table and last-updated line updated. No rule changed.
- 2026-11-18 — Phase 3 M5 merged (PR #31, `cd5d07a`); M6 complete on its branch; phase table and last-updated line updated. No rule changed.
- 2026-11-18 — Phase 3 M6 merged (PR #32, `0b39b39`); M7 complete on its branch; phase table and last-updated line updated. No rule changed.
- 2026-11-19 — Phase 3 M7 merged (PR #33, `4fbcbcc`); M8 complete on its branch; phase table and last-updated line updated. No rule changed.
- 2026-11-19 — Phase 3 M8 merged (PR #34, `92fcd05`); M9 complete on its branch; phase table and last-updated line updated. No rule changed.
- 2026-11-19 — Phase 3 M9 merged (PR #35, `8b19e76`); M10 partial on its branch; phase table and last-updated line updated. No rule changed.
- 2026-11-21 — Phase 3 M10 part 1 merged (PR #36, `e3c89da`); part 2 on its branch; phase table and last-updated line updated. No rule changed.
- 2026-11-21 — Phase 3 M11 on its branch (docs, security self-review); phase table and last-updated line updated. No rule changed.
- 2026-11-21 — Phase 3 Complete (M11 merged on the owner's instruction; ADR-049 moves the D9 benchmark to Phase 18); phase table and last-updated line updated. No rule changed.
- 2026-11-21 — Phase 4 plan proposed (ADR-050 to ADR-053 Proposed); phase table updated. No rule changed.
