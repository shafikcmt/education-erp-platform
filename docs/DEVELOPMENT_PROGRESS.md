# Development Progress

> Updated at the end of **every** session (`CLAUDE.md` §18). Status vocabulary: `Not started`, `Planned`, `In progress`, `Partial`, `Blocked`, `Complete`, `Approved`.
> Append session entries; never delete history.

## Current state

- **Current phase:** Phase 1 — Repository foundation & infrastructure
- **Phase 0 status:** Approved (owner merged PR #1 into `main`, 2026-11-05).
- **Phase 1 status:** Complete.
  - **PR #2 was merged into `main` by the owner (`shafikcmt`) at 2026-11-05 18:42:43 UTC** as merge commit `cb2383e`. Its head was `41b7e55`, with CI 8/8 green.
  - The Session 4 review fixes (`91b34d3`) were pushed after that merge, so they are carried by the **follow-up PR** from `fix/phase-01-review-hardening` (not merged).
  - Phase 1 becomes `Approved` when the owner confirms approval and merges the follow-up PR.
- **Application code:** platform foundation only (`core`, minimal `identity.User`). No business modules.

## Phase status

| Phase | Name | Status | PR(s) | Notes |
|---|---|---|---|---|
| 0 | Documentation & architecture baseline | Approved | [PR #1](https://github.com/shafikcmt/education-erp-platform/pull/1) | Merged into `main` by owner |
| 1 | Repository foundation & infrastructure | Complete | [PR #2](https://github.com/shafikcmt/education-erp-platform/pull/2) (merged) + review follow-up PR (open) | Follow-up PR awaiting owner approval |
| 2 | Authentication, users, roles & permissions | Planned | | Plan rev. 2 (`plans/PHASE_02_PLAN.md`) awaiting final owner approval; blocked on PR #12 merge |
| 3 | SaaS tenants, institutions & campuses | Not started | | |
| 4 | Module registry & feature entitlement engine | Not started | | |
| 5 | Customization Studio & institution configuration | Not started | | |
| 6 | Academic structure & student admission | Not started | | |
| 7 | Student, teacher & parent management | Not started | | |
| 8 | Attendance management | Not started | | |
| 9 | Examination & results | Not started | | |
| 10 | Fees & financial accounting | Not started | | |
| 11 | HR & payroll | Not started | | |
| 12 | Hostel, transport & library | Not started | | |
| 13 | LMS & online examinations | Not started | | |
| 14 | Notifications & communication | Not started | | |
| 15 | Reports & analytics | Not started | | |
| 16 | AI assistant | Not started | | |
| 17 | Institution-specific extensions & custom module builder | Not started | | |
| 18 | Security, performance & production readiness | Not started | | |
| 19 | Docker production deployment & CI/CD | Not started | | |

## Decisions awaiting owner approval

See `DECISION_LOG.md`.
- **Accepted 2026-11-05:** ADR-009, ADR-010, ADR-011 (with modification), ADR-012, ADR-013, ADR-014, ADR-015, ADR-021, ADR-029 (conditions verified), ADR-030 (TS 5.9 / ESLint 9 held temporarily).
- **Still Proposed/Open:** ADR-016–020, ADR-022–028.
- **Accepted 2026-11-05 (Phase 2 planning):** ADR-031, ADR-032, ADR-033 (with conditions), ADR-034, ADR-035, ADR-036 (IP privacy, Q7), ADR-037 (Q2–Q9).
- **Open with the Phase 2 plan rev. 2:** Q10 (TOTP manual-entry key, default not provided), Q11 (`@hookform/resolvers`), and final plan approval.

## Known gaps / open questions

- Price points, tier boundaries, trial length (ADR-024).
- Payment gateways for SaaS billing and fee collection (ADR-017).
- Hosting provider, region, data residency (ADR-019).
- Legal/compliance review for minors' data, retention periods, VAT/tax invoicing.
- **Security-event IP retention (ADR-036):** default 365 days and lawful basis are **pending legal review before production**. Nginx access logs contain plaintext client IPs; set their retention and rotation policy in Phase 19.
- Numeric NFR targets (latency, availability, RPO/RTO) are proposed, not approved.
- Institution-type preset content (especially madrasa variants and hostel profile defaults) needs validation with real institutions.
- Branch protection for `main` must be configured by the repository owner in GitHub settings (require the CI jobs listed in `DOCKER_DEPLOYMENT.md` §6).
- ESLint is held at 9.x (deprecated upstream) and TypeScript at 5.9; both are owner-approved as temporary, with upgrade triggers tracked in ADR-030.
- GitHub Actions warns that `astral-sh/setup-uv@v6` and `pnpm/action-setup@v4` run on the deprecated Node 20 runtime; bump them when Node 24 majors are available (ADR-030 tracking; Dependabot watches actions).
- `erp_app` still has DML on `django_migrations` (all tables get DML via default privileges). Runtime never needs to write it; restrict it with the Phase 3 RLS/grant migration helper.
- The dev Postgres image trusts local connections *inside its own container* (`pg_hba` image default). Network connections require SCRAM. Production uses a managed or hardened database (Phase 19).
- `beat` has no Docker healthcheck. Its dispatch was verified from logs in Session 4 (heartbeat sent and consumed); add a meaningful healthcheck in Phase 19.
- `s3_mirror` buffers one object at a time in memory, which is fine for dev/CI. Production-scale backup tooling and schedule: Phase 19.
- Compose builds in this cloud sandbox needed a registry mirror and a build-time CA (environment-specific, not committed). Normal Docker/GitHub environments need neither.

## Session log

### 2026-11-05 — Session 1 (Phase 0)
- Inspected repository: new project; single initial commit; only `README.md` containing the title line `# education-erp-platform` (heading preserved and expanded). Branches: `main`, `claude/dreamy-mendel-nt3d6d`. No other files, reports or docs existed.
- Created `CLAUDE.md` and documentation set: `README.md` (expanded), `docs/PROJECT_VISION.md`, `REQUIREMENTS.md`, `SYSTEM_ARCHITECTURE.md`, `TECH_STACK.md`, `DATABASE_DESIGN.md`, `ERD.md`, `MULTI_TENANT_ARCHITECTURE.md`, `MODULE_CATALOG.md`, `CUSTOMIZATION_ENGINE.md`, `SUBSCRIPTION_AND_BILLING.md`, `SECURITY.md`, `API_STANDARDS.md`, `FRONTEND_STANDARDS.md`, `AI_ASSISTANT.md`, `DOCKER_DEPLOYMENT.md`, `TESTING_STRATEGY.md`, `DEVELOPMENT_ROADMAP.md`, `DEVELOPMENT_PROGRESS.md`, `DECISION_LOG.md`.
- Recorded 8 accepted (owner-mandated) ADRs and 19 proposed/open ADRs.
- No application code, models, dashboards or migrations were created (per instruction).
- Tests/lint: not applicable (documentation only).
- **Next recommended task:** owner reviews docs and decides ADR-009 through ADR-014; then start Phase 1 (repository foundation & infrastructure).

### 2026-11-05 — Session 2 (Phase 0 approvals)
- Owner approved ADR-009, ADR-010, ADR-012, ADR-013, ADR-014. ADR-011 approved with modification: Django session authentication for the browser app; a separate future token path for mobile/third-party.
- `DECISION_LOG.md`: recorded precise decisions (transaction-scoped `set_config` via `core.db.tenant_atomic`, FORCE RLS with fail-closed policy, `erp_owner`/`erp_app`/`erp_platform` roles, campus/institution limits, cookie attributes, `core.ids.new_id()` abstraction, uv/pnpm specifics, layout). Added ADR-028 (Proposed) for mobile/third-party auth. No other ADR status changed.
- Updated `CLAUDE.md`, `SECURITY.md`, `API_STANDARDS.md`, `FRONTEND_STANDARDS.md`, `SYSTEM_ARCHITECTURE.md`, `MULTI_TENANT_ARCHITECTURE.md`, `DATABASE_DESIGN.md`, `TECH_STACK.md`, `DOCKER_DEPLOYMENT.md`, `SUBSCRIPTION_AND_BILLING.md`, `DEVELOPMENT_ROADMAP.md`. Removed the obsolete Next.js BFF token design.
- Added `docs/plans/PHASE_01_PLAN.md` (status Proposed).
- Opened the Phase 0 documentation PR [shafikcmt/education-erp-platform#1](https://github.com/shafikcmt/education-erp-platform/pull/1) into `main` (not merged; awaiting owner).
- Tests/lint: not applicable (documentation only).
- **Next recommended task:** owner approves the Phase 1 plan and answers Q1–Q8, merges the Phase 0 PR, then Phase 1 implementation starts.

### 2026-11-05 — Session 3 (Phase 1 implementation)
- Verified PR #1 merged: `main` at `b70a23c` contains all 22 Phase 0 files, identical to the reviewed branch. Created `feat/phase-01-foundation` from `main`.
- **Implemented:**
  - Monorepo tooling: pnpm workspace, `.nvmrc`, Prettier, Makefile, pre-commit, `.gitignore` / `.gitattributes` / `.editorconfig`, `.env.example` (dummy values).
  - **Backend:**
    - Django 5.2.19 with `dev`/`test`/`prod` settings via django-environ, and ADR-011 cookie/CSRF settings.
    - `core`: `ids.new_id()` (UUIDv7), abstract `BaseModel`, Problem Details errors with an `/api/` catch-all 404, pagination, `RequestIDMiddleware`, structlog JSON logs with redaction, Sentry init, `/healthz`, `/readyz`, `GET /api/v1/system/health/`, Celery app + `core.ping` + beat schedule, the `smoke_check` command, and the PostgreSQL extensions migration.
    - `identity.User` stub (approved Q2).
  - **DB roles (ADR-009):** `01-roles.sh` creates `erp_owner`, `erp_app` (NOSUPERUSER, NOBYPASSRLS, DML only, statement timeouts) and `erp_platform` (NOLOGIN, BYPASSRLS, reserved); installs extensions in the app DB and template1; sets default privileges.
  - **Frontend:** Next.js 16.4.5 + React 19.3 + Tailwind 4 + shadcn/ui-style components + next-intl (en/bn, RTL-ready); landing page and system page using the generated client; CSRF-aware API wrapper with no token storage.
  - **`packages/api-client`:** OpenAPI 3 schema + openapi-typescript types.
  - **Docker:** multi-stage, non-root images for backend and frontend; dev compose with 11 services (corrected in Session 4; originally written as 12), pinned images and read-only root filesystems; Nginx single origin on :8080.
  - **CI:** 8 GitHub Actions jobs, Dependabot, PR template.
- **Verification (actual results in this session):**
  - **Backend quality:**
    - `ruff check`: all checks passed; `ruff format --check`: 46 files formatted.
    - `mypy` (strict): no issues in 46 files.
    - import-linter: 2 contracts kept. A deliberate `uuid_utils` import was caught as BROKEN, then removed.
    - `makemigrations --check`: no changes. `pip-audit --strict`: no known vulnerabilities.
  - **Backend tests:** `pytest` 65 passed, coverage 96.28% (gate 85%), run as `erp_app`.
    - Negative control: running the role tests as `erp_owner` fails 5 of them, as intended.
    - The same suite passed against a fresh PostgreSQL bootstrapped the way CI does it (`PGHOST`); the bootstrap is idempotent.
  - **API contract:** `spectacular --validate --fail-on-warn`: ok; TypeScript client generated.
  - **Frontend:** Prettier clean; ESLint 0 warnings; `tsc`: ok; Vitest 10 passed; `next build`: ok.
  - **Stack:**
    - `docker compose down -v && up --wait`: all services healthy or completed in about 37 s (11 services; originally written as 12, corrected in Session 4).
    - `smoke_check`: database (`erp_app`, not superuser, no BYPASSRLS), cache, storage round-trip and Celery round-trip all ok.
    - `/readyz` returns 503 Problem Details with Redis stopped and 200 after restart.
    - All app containers run as non-root.
    - Object storage: the app identity is denied on other buckets.
  - **Playwright:** 14 passed (desktop + mobile Chromium: locale redirect, en/bn rendering, locale switcher, system page "ok" via the generated client, headers/probes/Problem Details through Nginx, axe with no serious violations).
  - **Images:**
    - The production backend image runs gunicorn + uvicorn under prod settings with a read-only rootfs, healthy, with JSON logs.
    - Trivy initially found fixable HIGH CVEs in base-image tooling (system pip/setuptools, bundled npm). These were removed; both images now have no fixable HIGH or CRITICAL vulnerabilities.
  - **Other:** gitleaks found no leaks in the committable tree; actionlint ok.
- **Deviations from the plan:** see `plans/PHASE_01_PLAN.md` §13 (notably D1: SeaweedFS instead of MinIO, ADR-029).
- **Not done / out of scope (by design):** tenancy models, RLS policies on real tables, `tenant_atomic` (Phase 3); login/MFA/RBAC (Phase 2); business modules; production deploy (Phase 19).
- **Next recommended task:** owner reviews the Phase 1 PR and its CI results and confirms ADR-029; then plan Phase 2 (authentication, users, roles & permissions).

### 2026-11-05 — Session 4 (Phase 1 review requested by owner)
- **Owner decisions:**
  - ADR-029 approved, conditional on verified bucket isolation, S3 compatibility, backup/restore and provider portability. All four were verified this session.
  - ADR-030 approved: TypeScript 5.9 and ESLint 9 held temporarily.
  - Both are recorded in `DECISION_LOG.md` with evidence and an upgrade-tracking table.
- **PR #2 CI (head `41b7e55`, run 42083300228): 8/8 jobs succeeded.**
  - Logs checked, not just the status: backend tests show the RLS write-block firing on the runner; e2e shows `14 passed`; Trivy shows every package clean.
  - Run 42083269020 was cancelled automatically by the concurrency group (superseded by the next push), as designed.
- **Fixes and additions from this review:**
  - **DB:** bootstrap revokes `CONNECT`/`TEMPORARY` from `PUBLIC` and grants `CONNECT` to `erp_owner` and `erp_app` only. The pytest DB mirrors this. New tests: TEMP tables denied; `ALTER`/`DROP`/`DISABLE RLS`/`CREATE INDEX` denied for `erp_app`. `smoke_check` asserts TEMP and CREATE are off.
  - **Prod config:**
    - API docs forced off whatever the environment says (previously `API_DOCS_ENABLED=true` would have exposed them publicly).
    - The secret-key guard now also rejects low-entropy keys (fewer than 5 distinct characters) and `django-insecure-` keys. Found because Django's checklist flagged the old test key.
    - `check --deploy --fail-level WARNING` passes; only W021 (HSTS preload) is silenced, deliberately.
  - **Storage:**
    - New `manage.py s3_mirror` for backup, restore and migration with SHA-256 verification (unit tests).
    - New opt-in S3 integration suite, added to CI `e2e-smoke` and `make s3-check`.
  - **Correction:** the stack has **11** services (9 long-running + 2 one-shot), not 12 as written in Session 3 and in the PR #2 description.
- **Verification (actual results this session):**
  - **Backend quality:**
    - ruff: all checks passed; format: 49 files formatted.
    - mypy (strict): no issues in 49 files.
    - import-linter: 2 kept, 0 broken.
    - `makemigrations --check`: no changes. pip-audit `--strict`: no known vulnerabilities.
  - **Backend tests:** pytest **84 passed, 9 skipped** (the skips are the opt-in S3 integration tests); coverage **93.40%** (gate 85%); run as `erp_app`.
  - **Production settings:** 13 tests passed, including Django's deployment checklist.
  - **API contract and frontend:**
    - `spectacular --validate --fail-on-warn`: ok; client drift: 0 files.
    - Prettier clean, ESLint ok, tsc ok, Vitest 10 passed.
    - actionlint: ok.
  - **Clean-volume start:** `down -v` (0 `erp_*` volumes left) → `up --wait` exit 0 in **38 s**. 11/11 services present; 8 healthy, `beat` up (no healthcheck), `migrate` and `objectstore-init` exited 0.
  - **Smoke check:** database (`erp_app`, superuser False, bypassrls False, temporary False, create_schema False), cache, storage and Celery all ok.
  - **Containers:** non-root (api/worker/beat 10001, web 1000, nginx 101); read-only rootfs confirmed on api, web and nginx.
  - **Role review (live DB):**
    - `migrate` as `erp_app` fails with `must be owner of table`; afterwards all migrations are still applied and all 9 tables intact.
    - Role attributes as designed; `erp_platform` cannot log in and has no password; passwords stored as SCRAM-SHA-256.
    - DB ACL `{erp_owner=CTc, erp_app=c}`; every public table owned by `erp_owner`; `erp_app` has only DELETE, INSERT, SELECT, UPDATE and no role memberships.
  - **ADR-029 conditions:**
    - S3 suite on SeaweedFS: **9/9**, including foreign-bucket list/put/get/delete denied, anonymous 403, tampered and expired presigned URLs 403, and bucket creation denied.
    - Same suite on RustFS: **7/7**; the 2 excluded tests need non-root credentials.
    - Backup → volume destroyed (0 objects) → restore: 3 objects / 6,293,612 bytes, SHA-256 identical, content types preserved.
    - Migration SeaweedFS → RustFS: identical; app switched to RustFS by environment variables only, and `smoke_check` storage passed.
  - **Images and repository:**
    - Trivy on rebuilt production images: no fixable HIGH or CRITICAL vulnerabilities in either image.
    - gitleaks over the full history of all branches: no leaks.
    - Committed-file audit: the only env file is `.env.example` (dummy values); no build artifacts, caches, keys or large binaries (largest tracked file: `pnpm-lock.yaml`, 276 KB).
  - **Playwright** on the fresh stack: **14 passed**.
  - **Celery beat → worker:** beat started 18:57:31, sent `core-heartbeat` at 19:02:31.701 (the 300 s interval), and the worker returned `pong` at 19:02:31.716.
- **Merge state discovered at the end of Session 4:**
  - PR #2 had already been merged by the owner at 18:42:43 UTC, before the review commit.
  - The review commit was cherry-picked onto a new branch `fix/phase-01-review-hardening` from `main` (`cb2383e`); it applied cleanly.
  - A follow-up PR was opened for owner approval. Not merged.
- **Dependabot (active since the merge put `dependabot.yml` on `main`):** 9 PRs were opened (#3–#11). Triage:
  - **Conflicts with accepted decisions (recommend closing):**
    - #11 Django 5.2 → 6.1 (ADR-003 LTS);
    - #5 Redis 7.4 → 8.10 (ADR-030);
    - #10 Nginx 1.28 → 1.31 (a mainline odd minor, not the stable line).
    - The follow-up PR adds `ignore` rules so these are not proposed again.
  - **Reasonable (owner review/merge separately):**
    - #3, #4, #6, #7, #8: GitHub Actions majors. They address the Node 20 runtime deprecation warning.
    - #9: Mailpit v1.33.0 (dev-only tool).
- **Next recommended task:** owner reviews and merges the follow-up PR and closes or merges the Dependabot PRs per the triage above; Phase 1 is then `Approved` and the Phase 2 plan (authentication, users, roles & permissions) is prepared for approval.

### 2026-11-05 — Session 5 (Phase 2 planning)
- **Merge verification:**
  - `main` is at `cb2383e` (the PR #2 merge). All 28 Phase 1 foundation files checked are present (137 tracked files).
  - **PR #12 (Phase 1 review follow-up) is still open, not merged** (CI green, mergeable). Its fixes are therefore **not yet on `main`**: prod API-docs and secret-key guards, DB TEMP/CONNECT hardening, ADR-029/030 Accepted, S3 isolation suite, `s3_mirror`, Dependabot ADR guards. The owner's message said the Phase 1 PR was merged; that matches PR #2, not PR #12.
- **Planning:**
  - Prepared `docs/plans/PHASE_02_PLAN.md` (Proposed). It covers:
    - the tenant-aware membership design (built in Phase 3, ADR-032);
    - the role and permission matrix for Super Admin, Institution Admin, Campus Admin, Teacher, Staff, Student and Parent;
    - the auth, session, MFA, password-reset, email-verification and audit design;
    - models, API endpoints, frontend screens, tests, dependencies and acceptance criteria.
  - Added ADR-031 to ADR-035 (Proposed). The roadmap Phase 2/3 sections were updated to match.
  - Work is on branch `docs/phase-02-plan`, stacked on PR #12's branch.
- **No code written.** Tests/lint: not applicable (documentation only).
- **Next recommended task:**
  1. Owner merges PR #12 and confirms Phase 1 `Approved`.
  2. Owner reviews the Phase 2 plan and answers Q1–Q9.
  3. After approval: implement on `feat/phase-02-auth-rbac` and open a separate PR.

### 2026-11-05 — Session 6 (Phase 2 plan revision 2)
- **Owner approvals recorded in `DECISION_LOG.md`:**
  - ADR-031, ADR-032, ADR-034 and ADR-035 Accepted; ADR-033 Accepted with conditions.
  - New Accepted ADR-036 (encrypted, access-restricted, retention-limited security IPs; Q7 conditions).
  - New Accepted ADR-037 (Q2–Q9: phone login → Phase 14, no public registration, breach check optional/off, server-side QR, 30 min / 12 h sessions, new sign-in notices, Django admin disabled).
  - Approved libraries recorded with version ranges in `TECH_STACK.md`: pyotp 2.10, cryptography 50.0.2, segno 1.6.6 (low release cadence noted), TanStack Query 5.106, react-hook-form 7.91, zod 4.6.
- **`plans/PHASE_02_PLAN.md` rev. 2:**
  - pluggable permission sources (§4.4); support-access design (§4.5); Phase 3 RLS consistency review (§4.6);
  - data-driven privileged-account MFA; reuse of Django security primitives (§6.10); IP privacy design (§6.9);
  - traceability of the owner's 10 additional requirements (§14); final implementation checklist (§15); acceptance criteria (§16).
- **Conflicts found and resolved in rev. 2:**
  - Rev. 1 returned an `otpauth://` URI, which contains the raw secret and so violates Q5. Rev. 2 makes enrollment QR-only, and the manual-entry key is open as Q10.
  - IP retention (ADR-036) is incompatible with an immutable audit table holding IPs. Audit IPs move to a separate, deletable encrypted side table.
  - Platform rows with `tenant_id NULL` would be blocked by the standard RLS policy in Phase 3. A dual-scope policy is defined for `rbac_role`, `rbac_rolepermission` and `audit_auditevent`.
  - `RolePermission` gains a nullable `tenant_id` in Phase 2, so Phase 3 needs no backfill.
- **Related docs aligned:** `CLAUDE.md` (`staff_member` role; privileged MFA; no implicit tenant access), `SECURITY.md`, `MULTI_TENANT_ARCHITECTURE.md` (support sessions, dual-scope tables), `REQUIREMENTS.md` (IAM-01/02/03/07/09; new IAM-10, IAM-11), `DATABASE_DESIGN.md`, `API_STANDARDS.md`, `DEVELOPMENT_ROADMAP.md` (Phase 2/3/14), `TECH_STACK.md`.
- **PR #12 is still open (not merged)**, so Phase 2 implementation remains blocked. The documentation branch `docs/phase-02-plan` stays stacked on PR #12's branch and is rebased onto `main` after PR #12 merges.
- **No application code written.** Tests/lint: not applicable (documentation only).
- **Next recommended task:**
  1. Owner merges PR #12 and confirms Phase 1 `Approved`.
  2. Owner answers Q10 and Q11 and gives final approval of plan rev. 2.
  3. Rebase the docs branch onto `main`, then implement on `feat/phase-02-auth-rbac` with a separate PR.

