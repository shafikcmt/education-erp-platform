# Development Progress

> Updated at the end of **every** session (`CLAUDE.md` §18). Status vocabulary: `Not started`, `Planned`, `In progress`, `Partial`, `Blocked`, `Complete`, `Approved`.
> Append session entries; never delete history.

## Current state

- **Current phase:** Phase 8 — Attendance management: **In progress** (plan **Approved** by the owner 2026-11-28 with all recommendations, ADR-076 to ADR-081 Accepted; plan merged in PR [#87](https://github.com/shafikcmt/education-erp-platform/pull/87); M1 merged in PR [#88](https://github.com/shafikcmt/education-erp-platform/pull/88); M2 merged in PR [#89](https://github.com/shafikcmt/education-erp-platform/pull/89); M3 merged in PR [#90](https://github.com/shafikcmt/education-erp-platform/pull/90); M4 merged in PR [#91](https://github.com/shafikcmt/education-erp-platform/pull/91); M5 merged in PR [#92](https://github.com/shafikcmt/education-erp-platform/pull/92); M6 merged in PR [#93](https://github.com/shafikcmt/education-erp-platform/pull/93); M7 merged in PR [#94](https://github.com/shafikcmt/education-erp-platform/pull/94); M8 on `feat/phase-08-m8`). Phase 7 **Approved** (2026-11-28; ADR-075). History of this line: Phase 7 — Student, teacher & parent management: **Approved** by the owner (2026-11-28, all recommendations; ADR-075; M1–M10 merged, M10 in PR [#86](https://github.com/shafikcmt/education-erp-platform/pull/86), squash `9844695`). **Phase 8 — Attendance management: plan Proposed** (`docs/plans/PHASE_08_PLAN.md`, ADR-076 to ADR-080 Proposed); no Phase 8 code before the owner approves the plan. History of this line: Phase 6 — Academic structure & student admission: **Approved** by the owner (2026-11-24, all recommendations; ADR-067). **Phase 7 — Student, teacher & parent management: Complete, awaiting the owner's approval** (2026-11-27; M1–M10; security self-review `docs/security/PHASE_07_SECURITY_REVIEW.md`; plan **Approved** 2026-11-26 with all recommended answers; ADR-068 to ADR-074 Accepted). **Phase 8 is not started.** History of this line: Complete, awaiting approval 2026-11-24 (M1–M8; security self-review `docs/security/PHASE_06_SECURITY_REVIEW.md`). Plan **Approved** 2026-11-23 with all recommended answers; ADR-063 to ADR-066 Accepted. Phase 5 **Approved** (2026-11-23). History of this line: plan Proposed 2026-11-23.
- **Phase 4:** **Approved** by the owner (2026-11-22); M1–M7 merged (PRs #44–#50). History of this line: (M1 [#44](https://github.com/shafikcmt/education-erp-platform/pull/44), M2 [#45](https://github.com/shafikcmt/education-erp-platform/pull/45) M3 [#46](https://github.com/shafikcmt/education-erp-platform/pull/46) M4 [#47](https://github.com/shafikcmt/education-erp-platform/pull/47) and M5 [#48](https://github.com/shafikcmt/education-erp-platform/pull/48) merged; M6 on `feat/phase-04-m6`). **Tenant hosts remain disabled.**
- **Phase 3:** **Approved** by the owner (2026-11-21). The milestone history below is kept as written.
  - **M1 (incl. O1): Complete** and merged into `main` (PR [#17](https://github.com/shafikcmt/education-erp-platform/pull/17), squash `3108824`).
  - **M2 (tenancy data model): Complete** and merged into `main` (PR [#18](https://github.com/shafikcmt/education-erp-platform/pull/18), squash `3616778`; Sessions 16–18).
  - **M3 (host policy, tenant request lifecycle, durable audit): Complete** and merged into `main` (PR [#29](https://github.com/shafikcmt/education-erp-platform/pull/29), squash `066b727`; Sessions 20 and 22). Deferred test items are listed under "Known gaps". **Tenant hosts remain disabled.**
  - **M4 (memberships, invitations, role assignments, tenant roles): Complete** and merged into `main` (PR [#30](https://github.com/shafikcmt/education-erp-platform/pull/30), squash `14a54d6`; Sessions 21–22).
  - **M5 (support sessions, restricted owner mode): Complete** and merged into `main` (PR [#31](https://github.com/shafikcmt/education-erp-platform/pull/31), squash `cd5d07a`; Session 23).
  - **M6 (dual-scope RLS on roles and the audit log, P10 in every scope): Complete** and merged into `main` (PR [#32](https://github.com/shafikcmt/education-erp-platform/pull/32), squash `0b39b39`; Session 24).
  - **M7 (declared Celery tasks, TenantTask, key helpers, I/O guard, support expiry sweep): Complete** and merged into `main` (PR [#33](https://github.com/shafikcmt/education-erp-platform/pull/33), squash `4fbcbcc`; Session 25).
  - **M8 (tenant-host and platform APIs, provisioning, suspension, limits, OpenAPI and client): Complete** and merged into `main` (PR [#34](https://github.com/shafikcmt/education-erp-platform/pull/34), squash `92fcd05`; Session 26).
  - **M9 (frontend screens of plan §13, en + bn): Complete** and merged into `main` (PR [#35](https://github.com/shafikcmt/education-erp-platform/pull/35), squash `8b19e76`; Session 27).
  - **M10 (shared isolation evidence, two-tenant E2E, K3, benchmark): Partial**. Part 1 merged (PR [#36](https://github.com/shafikcmt/education-erp-platform/pull/36), squash `e3c89da`; Session 28); part 2 merged (PR [#41](https://github.com/shafikcmt/education-erp-platform/pull/41), squash `c6c1283`; Session 29: daily denial report, Bengali/mobile tenant-host E2E, unknown-host 404). Done: two-tenant E2E, K3 through the stack, the tenant-host MFA fix, threat-model and §23 evidence (`docs/security/PHASE_03_ISOLATION_EVIDENCE.md`). **Missing:** the D9 isolation-overhead benchmark, mobile and Bengali tenant-host E2E, prefork K6, and monitoring alerts (plan N93).
  - **M11 (docs, security self-review, Phase 3 approval PR): Complete** on `feat/phase-03-m11` (Session 29). **Not merged without the owner's approval** (plan §21 #12).
- **Phase 2 status:** **Approved**. The owner authorized the merge, and PR #15 was squash-merged into `main` as `2d61e83` on 2026-11-07. The merged tree is identical to the reviewed head `2cf3670`, and CI was 8/8 green (see Session 10).
- **Phase 1 status:** **Approved** by the owner on 2026-11-06 (see Session 8). The history below is kept as written.
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
| 1 | Repository foundation & infrastructure | Approved | [PR #2](https://github.com/shafikcmt/education-erp-platform/pull/2), [PR #12](https://github.com/shafikcmt/education-erp-platform/pull/12) (both merged) | Owner approval 2026-11-06 |
| 2 | Authentication, users, roles & permissions | Approved | [PR #13](https://github.com/shafikcmt/education-erp-platform/pull/13) (plan, merged), [PR #15](https://github.com/shafikcmt/education-erp-platform/pull/15) (implementation + security-review fixes, merged as `2d61e83`) | Owner-authorized merge 2026-11-07 after final security review (ADR-040) |
| 3 | SaaS tenants, institutions & campuses | Approved | [PR #16](https://github.com/shafikcmt/education-erp-platform/pull/16) (plan), [PR #17](https://github.com/shafikcmt/education-erp-platform/pull/17) (M1, merged `3108824`), [PR #18](https://github.com/shafikcmt/education-erp-platform/pull/18) (M2, merged `3616778`), [PR #29](https://github.com/shafikcmt/education-erp-platform/pull/29) (M3, merged `066b727`), [PR #30](https://github.com/shafikcmt/education-erp-platform/pull/30) (M4, merged `14a54d6`), [PR #31](https://github.com/shafikcmt/education-erp-platform/pull/31) (M5, merged `cd5d07a`), [PR #32](https://github.com/shafikcmt/education-erp-platform/pull/32) (M6, merged `0b39b39`), [PR #33](https://github.com/shafikcmt/education-erp-platform/pull/33) (M7, merged `4fbcbcc`), [PR #34](https://github.com/shafikcmt/education-erp-platform/pull/34) (M8, merged `92fcd05`), [PR #35](https://github.com/shafikcmt/education-erp-platform/pull/35) (M9, merged `8b19e76`); `feat/phase-03-m10` (M10) | **Approved** (owner, 2026-11-21; M1–M11; D9 benchmark moved to Phase 18, ADR-049); M5–M11 not started |
| 4 | Module registry & feature entitlement engine | Approved | [PR #43](https://github.com/shafikcmt/education-erp-platform/pull/43) (plan), [PR #44](https://github.com/shafikcmt/education-erp-platform/pull/44) (M1, merged `10d3365`), [PR #45](https://github.com/shafikcmt/education-erp-platform/pull/45) (M2, merged `e1465f5`), [PR #46](https://github.com/shafikcmt/education-erp-platform/pull/46) (M3, merged `3a7e6a5`), [PR #47](https://github.com/shafikcmt/education-erp-platform/pull/47) (M4, merged `d97634f`), [PR #48](https://github.com/shafikcmt/education-erp-platform/pull/48) (M5, merged `aa4b8f6`), [PR #49](https://github.com/shafikcmt/education-erp-platform/pull/49) (M6, merged `f8c924b`), [PR #50](https://github.com/shafikcmt/education-erp-platform/pull/50) (M7, merged `983a9e4`) | **Approved** (owner, 2026-11-22) |
| 5 | Customization Studio & institution configuration | Approved | [PR #51](https://github.com/shafikcmt/education-erp-platform/pull/51) (plan, merged `15eadb0`), [PR #52](https://github.com/shafikcmt/education-erp-platform/pull/52) (M1, merged `cd6f643`), [PR #53](https://github.com/shafikcmt/education-erp-platform/pull/53) (M2, merged `98f2ba8`), [PR #54](https://github.com/shafikcmt/education-erp-platform/pull/54) (M3, merged `eeef420`), [PR #55](https://github.com/shafikcmt/education-erp-platform/pull/55) (M4, merged `121bbff`), [PR #56](https://github.com/shafikcmt/education-erp-platform/pull/56) (M5, merged `4914529`), [PR #57](https://github.com/shafikcmt/education-erp-platform/pull/57) (M6, merged `940ec47`), [PR #58](https://github.com/shafikcmt/education-erp-platform/pull/58) (M7, merged `662986c`); [PR #59](https://github.com/shafikcmt/education-erp-platform/pull/59) (M8, merged `1d6e227`) | **Approved** (owner, 2026-11-23); ADR-061, ADR-062 Accepted |
| 6 | Academic structure & student admission | In progress | [PR #61](https://github.com/shafikcmt/education-erp-platform/pull/61) (plan, merged `8f284ff`), [PR #62](https://github.com/shafikcmt/education-erp-platform/pull/62) (M1, merged `7dc28fc`), [PR #63](https://github.com/shafikcmt/education-erp-platform/pull/63) (M2, merged `4f5e564`), [PR #64](https://github.com/shafikcmt/education-erp-platform/pull/64) (M3, merged `c12d3b7`), [PR #65](https://github.com/shafikcmt/education-erp-platform/pull/65) (M4, merged `b345b21`), [PR #66](https://github.com/shafikcmt/education-erp-platform/pull/66) (M5, merged `43a49fc`), [PR #67](https://github.com/shafikcmt/education-erp-platform/pull/67) (M6, merged `85ae32f`), [PR #68](https://github.com/shafikcmt/education-erp-platform/pull/68) (M7, merged `8e3a302`), [PR #69](https://github.com/shafikcmt/education-erp-platform/pull/69) (M8, merged `ea35c4f`) | **Approved** (owner, 2026-11-24; ADR-067); `timetable` moved to Phase 7 |
| 7 | Student, teacher & parent management | Approved | [PR #71](https://github.com/shafikcmt/education-erp-platform/pull/71) (plan, merged `dc4fcd3`); [PR #72](https://github.com/shafikcmt/education-erp-platform/pull/72) (M1, merged `f10a734`); [PR #73](https://github.com/shafikcmt/education-erp-platform/pull/73) (M2, merged `3943fe6`); [PR #74](https://github.com/shafikcmt/education-erp-platform/pull/74) (M3, merged `62c99d5`); [PR #75](https://github.com/shafikcmt/education-erp-platform/pull/75) (M4, merged `603a69b`); [PR #76](https://github.com/shafikcmt/education-erp-platform/pull/76) (M5, merged `49b70e8`); [PR #77](https://github.com/shafikcmt/education-erp-platform/pull/77) (M6, merged `cb9459b`); [PR #78](https://github.com/shafikcmt/education-erp-platform/pull/78) (M7, merged `b1c584e`); [PR #84](https://github.com/shafikcmt/education-erp-platform/pull/84) (M8, merged `58ca614`); [PR #85](https://github.com/shafikcmt/education-erp-platform/pull/85) (M9, merged `ad42b55`); [PR #86](https://github.com/shafikcmt/education-erp-platform/pull/86) (M10, merged `9844695`) | **Approved** (owner, 2026-11-28; ADR-075); plan Approved 2026-11-26 (ADR-068–074) |
| 8 | Attendance management | In progress | [PR #87](https://github.com/shafikcmt/education-erp-platform/pull/87) (plan, merged `138c35e`); [PR #88](https://github.com/shafikcmt/education-erp-platform/pull/88) (M1, merged `5113fc7`); [PR #89](https://github.com/shafikcmt/education-erp-platform/pull/89) (M2, merged `b750304`); [PR #90](https://github.com/shafikcmt/education-erp-platform/pull/90) (M3, merged `69fb10e`); [PR #91](https://github.com/shafikcmt/education-erp-platform/pull/91) (M4, merged `04962fc`); [PR #92](https://github.com/shafikcmt/education-erp-platform/pull/92) (M5, merged `a2e8172`); [PR #93](https://github.com/shafikcmt/education-erp-platform/pull/93) (M6, merged `e53068d`); [PR #94](https://github.com/shafikcmt/education-erp-platform/pull/94) (M7, merged `7632494`); `feat/phase-08-m8` (M8) | Plan Approved 2026-11-28 (ADR-076–081) |
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
- **Accepted 2026-11-06:** ADR-038 (manual MFA key with strict conditions, Q10), ADR-039 (`@hookform/resolvers`, Q11).
- **Resolved 2026-11-06:** Phase 1 approved; Phase 2 plan rev. 3 approved; PR #13 merged.
- ~~**Open:** owner review of the Phase 2 implementation (PR #15).~~ Resolved: approved and merged on 2026-11-07.
- **Proposed 2026-11-08 (Phase 3 planning):** ADR-041 (host-based tenant resolution and the enablement gate), ADR-042 (tenant context lifecycle), ADR-043 (no runtime BYPASSRLS; amends ADR-009 §5), ADR-044 (memberships and scoped role assignments), ADR-045 (support sessions), ADR-046 (RLS policy catalogue and CI enforcement). Owner questions: plan §15 Q1–Q12.
- **Accepted 2026-11-08 (Phase 3 final approval):**
  - ADR-041–047 Accepted and the Phase 3 plan rev. 3 Approved.
  - ADR-009 stays Accepted; its §5 third bullet is amended by ADR-043, recorded in an append-only note.
  - `CLAUDE.md` §10 item 3 updated.
- **2026-11-08 (Phase 3 plan rev. 3):**
  - ADR-041–047 approved in principle; D1–D9 decided (plan §17.2).
  - ADR-009 stays Accepted; an append-only note records the pending §5 amendment.
  - **Open:** the owner's final approval of the plan; the production domain (D1, needed only to enable tenant hosts in production).
- **2026-11-08 (Phase 3 plan rev. 2):**
  - The owner approved Q1–Q12 **in principle**; ADR-047 records the answers.
  - Runtime BYPASSRLS was **not approved**. ADR-043 rev. 2 instead keeps `erp_platform` unused and introduces the platform operation catalogue.
  - ADR-041 to ADR-047 are Proposed, awaiting final approval.
  - Remaining decisions are D1–D9 (plan §17.2). The production platform domain (D1) is needed before tenant hosts can be enabled in production.

### 2026-11-22 — Session 31 (continued): Phase 5 M7
- **M6:** [PR #57](https://github.com/shafikcmt/education-erp-platform/pull/57) — CI **8/8 success**; squash-merged → **`940ec47`** (tree identical to the head).
- **M7 (`feat/phase-05-m7`):** Customization Studio UI at `/studio` (settings and terminology with draft/publish/restore; custom fields; JSON editors for rules, forms, workflows and templates with test runner and preview; numbering); DynamicForm renderer (server-decided visibility and validation); notification bell; onboarding checklist on the dashboard; en + bn.
- **Deviations (plan §13.7):** visual builders are not built (JSON editors in v1); the onboarding wizard is a checklist; self-service sign-up moves to M8.
- **Verification (local):** frontend `tsc`, ESLint, Prettier clean; Vitest **46 passed** (6 new); `next build` succeeded (route `/[locale]/studio`); the four starter bodies were saved and published through the real services once (scratch test, not committed). No backend change in M7, so the backend suite was not re-run beyond that check. The Studio UI has **not** yet been exercised end to end in a browser: that is the M8 E2E work.
- **Next:** M8 (self-service sign-up behind its flag; E2E for presets per institution type and publish/rollback; security self-review; Phase 5 completion).

### 2026-11-22 — Session 31 (continued): Phase 5 M8 (Phase 5 complete)
- **M7:** [PR #58](https://github.com/shafikcmt/education-erp-platform/pull/58) — CI **8/8 success**; squash-merged pinned to `f820daf` → **`662986c`** (tree identical to the head).
- **M8 (`feat/phase-05-m8`):** self-service sign-up behind `TENANCY_SIGNUP_ENABLED` (off): request, email confirmation, platform approval or rejection; **approval is mandatory** (ADR-061, Proposed); P23 enabled (anonymous, registry only), P25 retention sweep added; sign-up, confirmation and platform sign-ups pages (en + bn); E2E journey; security self-review `docs/security/PHASE_05_SECURITY_REVIEW.md`.
- **E2E finding fixed:** the admin's TOTP codes were replayed across Playwright workers and the server (correctly) counted them as wrong codes until the account locked, failing unrelated journeys. `freshTotp` now claims each step across workers (atomic `mkdir`); the Phase 5 journey uses one admin session.
- **Verification (local):** backend **1032 passed, 9 skipped** (10 new); ruff, format, mypy (323 files), import-linter 9/9, `makemigrations --check` clean; OpenAPI `--validate --fail-on-warn` clean and client regenerated; frontend `tsc`, ESLint, Prettier clean, Vitest **47 passed**, `next build` succeeded. **Full-stack Playwright (throwaway stack with tenant hosts and sign-up on): 37 passed, 4 skipped (mobile copies of desktop-only journeys), 0 failed, 0 flaky.** The committed `.env.example` keeps tenant hosts and sign-up off; the local `.env` was restored.
- **Phase 5 status:** **Complete**, awaiting the owner's approval. Phase 6 is not started.
- **Open questions for the owner:** ADR-061 (mandatory sign-up approval); re-checking the inviter's permission at invitation acceptance (from Phase 3).
- **Next:** owner review of Phase 5; then the Phase 6 plan (academic structure and student admission) only after approval.

### 2026-11-23 — Session 31 (continued): Phase 5 approved; inviter re-check
- **M8:** [PR #59](https://github.com/shafikcmt/education-erp-platform/pull/59) — CI **8/8 success**; squash-merged pinned to `04611cd` → **`1d6e227`** (tree identical to the head).
- **Owner:** "approve and continue develop same" — recorded as approval of Phase 5 together with the two recommendations put to the owner: ADR-061 (mandatory sign-up approval) Accepted, and the open Phase 3 question answered "yes" (ADR-062). The owner can correct this reading.
- **Fix (`fix/invitation-inviter-recheck`):** member-created invitations are re-authorised at acceptance (ADR-062): migration `tenancy/0008` adds `recheck_inviter` (default false, also in the database); acceptance fails with the generic answer and a durable `inviter_unauthorised` attempt when the inviter is suspended, has left, or lost the invite permission or a permission of the role. Provisioning owner invitations are not re-checked. 2 new tests.
- **Next:** Phase 6 plan (academic structure and student admission) as a proposal; implementation only after the owner approves it.

### 2026-11-23 — Session 31 (continued): Phase 6 plan proposed
- **Fix:** [PR #60](https://github.com/shafikcmt/education-erp-platform/pull/60) (inviter re-check, Phase 5 approval record) — CI **8/8 success**; squash-merged pinned to `3a80f36` → **`0dc1111`** (tree identical to the head).
- **Phase 6 plan proposed:** `docs/plans/PHASE_06_PLAN.md` (academics, `files`, admissions; eight owner questions with recommendations, including moving `timetable` to Phase 7). ADR-063 to ADR-065 Proposed.
- **Owner (2026-11-23):** "approved all ur recommendation, continue develop same" — the Phase 6 plan is **Approved** with all eight recommended answers (ADR-066); ADR-063 to ADR-065 Accepted. `timetable` moves to Phase 7; `files` is built in Phase 6.
- **Next:** M1 (`academics` data model, v2 presets, level-integrity hook, tests per preset).

### 2026-11-23 — Session 31 (continued): Phase 6 M1
- **Plan:** [PR #61](https://github.com/shafikcmt/education-erp-platform/pull/61) — CI **8/8 success**; squash-merged pinned to `b0e82c1` → **`8f284ff`** (tree identical to the head).
- **M1 (`feat/phase-06-m1`):** `academics` app (years, terms, the configurable unit tree, subjects, offerings with teachers) with RLS and composite tenant/institution keys; capability flags read in one place; v2 presets (organisational levels only) as the new defaults; publish check that refuses structure levels which strand units; role template updates.
- **Defect found and fixed (Phase 5 resolver):** configuration read inside a publishing transaction was cached and survived a rollback; the resolver no longer stores results while a publish is uncommitted.
- **Verification (local):** backend **1047 passed, 9 skipped** (13 new academics tests incl. one per institution type, isolation and the publish check); ruff, format, mypy (332 files), import-linter 9/9, `makemigrations --check` clean; OpenAPI unchanged (no API in M1).
- **Next:** M2 (academics API, OpenAPI and client).

### 2026-11-23 — Session 31 (continued): Phase 6 M2
- **M1:** [PR #62](https://github.com/shafikcmt/education-erp-platform/pull/62) — CI **8/8 success**; squash-merged pinned to `a8b189e` → **`7dc28fc`** (tree identical to the head).
- **M2 (`feat/phase-06-m2`):** academics API on tenant hosts (setup, years and terms, units, subjects, offerings and teachers); scope-filtered lists (404 outside the caller's institutions); OpenAPI and TypeScript client regenerated.
- **Verification (local):** backend **1050 passed, 9 skipped** (3 new API tests: module first, owner end-to-end, scopes and 404s); ruff, format, mypy (337 files), import-linter 9/9, `makemigrations --check` clean; OpenAPI `--validate --fail-on-warn` clean; frontend `tsc` clean.
- **Next:** M3 (`files` module: presigned upload/download, purposes and limits, scan states, quotas, P27).

### 2026-11-23 — Session 31 (continued): Phase 6 M3
- **M2:** [PR #63](https://github.com/shafikcmt/education-erp-platform/pull/63) — CI **8/8 success**; squash-merged pinned to `8ea5c0e` → **`4f5e564`** (tree identical to the head).
- **M3 (`feat/phase-06-m3`):** `files` module: declared purposes with type/size/count limits, presigned uploads bound to a server-chosen tenant key, verification task, scan states with a pluggable scanner (default unscanned, staff-only), short-lived attachment downloads, storage quota, P27 housekeeping; tenant-host API.
- **Verification (local):** backend **1057 passed, 9 skipped** (7 new files tests); ruff, format, mypy (352 files), import-linter 9/9, `makemigrations --check` clean; OpenAPI `--validate --fail-on-warn` clean and client regenerated; frontend `tsc` clean.
- **Known gap:** presigned uploads not yet exercised against the real object store from a browser (the stack doesn't expose it to browsers yet; M5/M8).
- **Next:** M4 (admissions: inquiries, cycles with form/workflow/merit/numbering bindings, staff-entered applications, review workflow).

### 2026-11-23 — Session 31 (continued): Phase 6 M4
- **M3:** [PR #64](https://github.com/shafikcmt/education-erp-platform/pull/64) — CI **8/8 success**; squash-merged pinned to `c097092` → **`c12d3b7`** (tree identical to the head).
- **M4 (`feat/phase-06-m4`):** `admissions` module back office: inquiries; cycles bound to published Studio artefacts (form, workflow, merit rule, numbering) with target units and capacity; staff-entered applications validated by the cycle's form; built-in or workflow review; decisions within capacity; offer answers with the acceptance hook for Phase 7; API.
- **Verification (local):** backend **1064 passed, 9 skipped** (7 new admissions tests); ruff, format, mypy (363 files), import-linter 9/9, `makemigrations --check` clean; OpenAPI `--validate --fail-on-warn` clean (enum overrides for statuses) and client regenerated; frontend `tsc` clean.
- **Next:** M5 (public application flow on tenant hosts: open cycles, form, email verification, status link, document uploads, abuse controls, P26).

### 2026-11-23 — Session 31 (continued): Phase 6 M5
- **M4:** [PR #65](https://github.com/shafikcmt/education-erp-platform/pull/65) — CI **8/8 success**; squash-merged → **`b345b21`**.
- **M5 (`feat/phase-06-m5`):** public application flow on tenant hosts (plan §13.5 D24–D30):
  - open cycles, form and visibility; apply (draft) → email verification → personal status link;
  - offer answers and document uploads with the status link;
  - abuse controls (per-IP 429, silent per-email limit and honeypot, hashed single-use tokens);
  - staff document list/download; the workflow starts at review for public applications;
  - P26 housekeeping enabled (draft purge, cycle closing).
- **Verification (local):** backend **1071 passed, 9 skipped** (7 new public-flow tests); ruff, format, mypy (367 files), import-linter 9/9, `makemigrations --check` clean; OpenAPI `--validate --fail-on-warn` clean and client regenerated; frontend `tsc` clean. GitHub CI: pending (see the PR).
- **Next:** M6 (admission tests and scores, the merit list with the `admissions.merit` rule, offers).

### 2026-11-23 — Session 31 (continued): Phase 6 M6
- **M5:** [PR #66](https://github.com/shafikcmt/education-erp-platform/pull/66) — CI **8/8 success**; squash-merged pinned to `bed198b` → **`43a49fc`** (tree identical to the head).
- **M6 (`feat/phase-06-m6`):** admission tests, seats and scores (plan §13.6 D31–D37):
  - the evaluated state with the total score;
  - the merit list, ranked by the cycle's sandboxed merit rule or the total;
  - publishing creates frozen versions (MFA and step-up);
  - offers go down the ranking, and a declined seat moves to the next applicant automatically;
  - the applicant's status page lists their tests.
- **Verification (local):** backend **1078 passed, 9 skipped** (7 new merit tests); ruff, format, mypy (369 files), import-linter 9/9, `makemigrations --check` clean; OpenAPI `--validate --fail-on-warn` clean and client regenerated; frontend `tsc` clean. GitHub CI: pending (see the PR).
- **Next:** M7 (frontend: academic setup, admissions back office, public pages; en and bn).

### 2026-11-24 — Session 31 (continued): Phase 6 M7
- **M6:** [PR #67](https://github.com/shafikcmt/education-erp-platform/pull/67) — CI **8/8 success**; squash-merged pinned to `88c1296` → **`85ae32f`** (tree identical to the head).
- **M7 (`feat/phase-06-m7`):** frontend for Phase 6 in en and bn (plan §13.7 D38–D43):
  - the academics page (years, subjects, unit tree in the tenant's terminology);
  - the admissions back office (cycles, applications, tests and scores, merit lists with step-up publishing, offers, documents, inquiries);
  - public `/apply`, `/apply/verify` and `/apply/status` pages on tenant hosts.
- Small API additions: `level_labels` on academics setup, the institution test list, and `unit_name` on targets.
- CSP: an optional, validated upload origin (`FILES_UPLOAD_ORIGIN`, empty by default).
- **Verification (local):**
  - backend **1078 passed, 9 skipped**; ruff, format, mypy (369 files), import-linter 9/9 and `makemigrations --check` are clean; OpenAPI is regenerated;
  - frontend: `tsc`, ESLint and Prettier are clean, vitest **48 passed**, and `next build` succeeds.
  - These screens have **not yet been run in a real browser**: that is the M8 E2E.
  - GitHub CI: pending (see the PR).
- **Next:** M8 (E2E through the real stack: structures per preset, the public journey to an accepted offer with a real upload; docs; security self-review; Phase 6 complete).

### 2026-11-24 — Session 31 (continued): Phase 6 M8 — Phase 6 Complete
- **M7:** [PR #68](https://github.com/shafikcmt/education-erp-platform/pull/68) — CI **8/8 success**; squash-merged pinned to `3d5e67e` → **`8e3a302`** (tree identical to the head).
- **M8 (`feat/phase-06-m8`):** plan §13.8 D44–D46.
  - **Real-stack E2E** of the whole admission journey: a madrasa structure in its own terminology; a published form and review workflow; apply, email verification and status link; a **real presigned upload** to the object store, verified by the worker and downloadable by staff; review workflow, test score, merit list (step-up) and offer; acceptance.
  - **Fixes found by running it:**
    - a workflow control on applications;
    - status links re-read on `hashchange`;
    - `no-cors` multipart upload;
    - a label collision.
  - The CI E2E stack now sets the object store's public origin.
  - **Security self-review:** `docs/security/PHASE_06_SECURITY_REVIEW.md`.
- **Verification (local):**
  - backend **1078 passed, 9 skipped**, all gates clean;
  - frontend `tsc`, ESLint and Prettier clean, vitest **49 passed**, `next build` OK;
  - **E2E (local real stack): 38 passed, 5 skipped** (the skips are per-project, as before), including the new admissions journey.
  - GitHub CI: pending (see the PR).
- **Phase 6 status:** **Complete**, awaiting the owner's approval. **Phase 7 is not started.**
- **Open questions for the owner** (self-review §3):
  1. Automatic offer to the next applicant on a decline (current) or a manual step?
  2. A separate score-only permission for exam controllers?

### 2026-11-24 — Session 31 (continued): Phase 6 approved
- **M8:** [PR #69](https://github.com/shafikcmt/education-erp-platform/pull/69) — CI **8/8 success**; squash-merged pinned to `0905356` → **`ea35c4f`** (tree identical to the head).
- **Owner (2026-11-24):** "approval all ur recomendation develop same". **Phase 6 Approved**, and ADR-067 Accepted:
  - the automatic offer on decline is kept;
  - the new score-only permission `admissions.test.score` (MFA): the exam controller gets scores only; owners, institution admins and admission officers get both codes.
- **This branch (`fix/phase-06-approval`):**
  - the permission and role templates (89 codes);
  - scoring, the seat-list read and the institution test list now need `admissions.test.score`, while scheduling and seating keep `admissions.test.manage`;
  - the UI follows the same split;
  - tests and docs.
- **Next:** the Phase 7 plan (student, teacher and parent management, plus `timetable`) as a proposal; implementation only after the owner approves it.

### 2026-11-24 — Session 31 (continued): Phase 7 plan proposed
- **Approval fix:** [PR #70](https://github.com/shafikcmt/education-erp-platform/pull/70) squash-merged pinned to `8f38d19` → **`ce4129d`** (tree identical to the head).
  - CI ended 8/8 green, but the first run of the stack E2E job **failed after 14 minutes**. I could not read which test failed: the log archive host is blocked from this environment.
  - The same branch passed the full local real-stack E2E (38 passed). The re-run of the failed job passed (8/8).
  - This is recorded as a **possible flaky E2E** to watch.
- **Phase 7 plan proposed:** `docs/plans/PHASE_07_PLAN.md` covers students, guardians and enrollments, staff, the portal, the timetable, conversion from admission, bulk import and relationship scopes. It has eight owner questions with recommendations. ADR-068 to ADR-073 are Proposed.
- **Next:** the owner's decision on the plan and Q1–Q8. No Phase 7 code is written before approval.
- **Owner (2026-11-26):** "approval all ur recommended and continue develop same". The Phase 7 plan is **Approved** with all eight recommended answers (ADR-074); ADR-068 to ADR-073 Accepted. **Next:** M1 (`students` data model).

### 2026-11-26 — Session 31 (continued): Phase 7 M1
- **Plan:** [PR #71](https://github.com/shafikcmt/education-erp-platform/pull/71) — CI 8/8; squash-merged → **`dc4fcd3`** (tree identical to the head).
- **M1 (`feat/phase-07-m1`):** the `students` app (plan §16.1 E1–E7):
  - students, guardians (tenant-wide, N-N links) and enrollments, with RLS and composite keys;
  - numbering from the Studio `student` sequence;
  - guardian matching within the tenant, and merging;
  - enrollment rules;
  - 12 permission codes and role templates (teachers `view_assigned` only);
  - the `max_active_students` limit key.
- **Verification (local):** backend **1086 passed, 9 skipped** (8 new students tests); ruff, format, mypy (376 files), import-linter 9/9 and `makemigrations --check` are clean; OpenAPI is unchanged (no API yet). GitHub CI: pending (see the PR).
- **Next:** M2 (relationship scopes and the students/guardians API).

### 2026-11-26 — Session 31 (continued): Phase 7 M2
- **M1:** [PR #72](https://github.com/shafikcmt/education-erp-platform/pull/72) — CI 8/8; squash-merged → **`f10a734`** (tree identical to the head).
- **M2 (`feat/phase-07-m2`):** relationship scopes (one selector for staff scope, taught units, children and self; campus-scoped roles handled), guardian contact details limited to the guardian's own link, and the students and guardians API with OpenAPI and the client (plan §16.2 E8–E12).
- **Verification (local):** backend **1093 passed, 9 skipped** (7 new object-level API tests); ruff, format, mypy (382 files), import-linter 9/9 and `makemigrations --check` are clean; OpenAPI `--validate --fail-on-warn` is clean and the client is regenerated. GitHub CI: pending (see the PR).
- **Next:** M3 (`staff`: departments, designations, profiles, class-teacher advisors as an assignment source).

### 2026-11-26 — Session 31 (continued): Phase 7 M3
- **M2:** [PR #73](https://github.com/shafikcmt/education-erp-platform/pull/73) — CI 8/8; squash-merged pinned to `32c0b44` → **`3943fe6`** (tree identical to the head).
- **M3 (`feat/phase-07-m3`):** new `staff` app: departments, designations, staff profiles (login optional), class-teacher advisors registered as a source of "the students I teach or advise"; profile visibility (scope, home campus, own); 4 permission codes and role templates; staff API with OpenAPI and the client; person validation shared through `core.people` (plan §16.3 E13–E20).
- **Verification (local):** backend **1103 passed, 9 skipped** (10 new staff tests: 5 service, 5 API with object-level allowed and denied cases); ruff, format, mypy, import-linter 9/9 and `makemigrations --check` are clean; OpenAPI `--validate --fail-on-warn` is clean and the client is regenerated; frontend `tsc` clean. GitHub CI: pending (see the PR).
- **Next:** M4 (admission → student conversion handler; enrollment from accepted applications; staff application-entry API).

### 2026-11-26 — Session 31 (continued): Phase 7 M4
- **M3:** [PR #74](https://github.com/shafikcmt/education-erp-platform/pull/74) — CI 8/8; squash-merged pinned to `a952ee5` → **`62c99d5`** (tree identical to the head).
- **M4 (`feat/phase-07-m4`):** accepted applications become students through the admissions hook and a `students` tenant task: the student, the primary guardian (matched within the tenant), custom values with matching keys, and the enrollment when the admitted unit is a leaf; idempotent; failures audited; staff retry endpoint. The staff application-entry API already existed (Phase 6 M4) (plan §16.4 E21–E27).
- **Verification (local):** backend **1108 passed, 9 skipped** (5 new conversion tests); ruff, format, mypy, import-linter 9/9 and `makemigrations --check` clean; OpenAPI `--validate --fail-on-warn` clean and the client regenerated. GitHub CI: pending (see the PR).
- **Next:** M5 (lifecycle: transfer, withdraw, promotion, transfer certificate, alumni, ID cards).

### 2026-11-26 — Session 31 (continued): Phase 7 M5
- **M4:** [PR #75](https://github.com/shafikcmt/education-erp-platform/pull/75) — CI 8/8; squash-merged pinned to `48ec2ab` → **`603a69b`** (tree identical to the head).
- **M5 (`feat/phase-07-m5`):** lifecycle: move within the year, withdraw, transfer certificates (new table, Studio numbering), promotion with rule suggestions, staff confirmation and one-transaction apply (step-up), alumni on completion, and ID card / transfer certificate HTML from Studio templates (plan §16.5 E28–E33).
- **Verification (local):** backend **1112 passed, 9 skipped** (4 new lifecycle tests) before a lint-only fix in the new test file, which was re-run (4 passed); ruff, format, mypy, import-linter 9/9 and `makemigrations --check` clean; OpenAPI `--validate --fail-on-warn` clean and the client regenerated. GitHub CI: pending (see the PR).
- **Next:** M6 (bulk import: CSV and XLSX through `openpyxl`, dry run, row report, P28 housekeeping).

### 2026-11-26 — Session 31 (continued): Phase 7 M6
- **M5:** [PR #76](https://github.com/shafikcmt/education-erp-platform/pull/76) — CI 8/8; squash-merged pinned to `9d6ff64` → **`49b70e8`** (tree identical to the head).
- **M6 (`feat/phase-07-m6`):** bulk import of students (with guardian and enrollment) and staff from CSV or XLSX: files upload, mapping, dry run, apply with atomic rows, row report (formula-safe CSV), step-up, P28 housekeeping; new dependency `openpyxl` (ADR-074 Q3) (plan §16.6 E34–E39).
- **Verification (local):** backend **1118 passed, 9 skipped** (6 new import tests); ruff, format, mypy, import-linter 9/9 and `makemigrations --check` clean; OpenAPI `--validate --fail-on-warn` clean (after an enum override for the import status) and the client regenerated. GitHub CI: pending.
- **Known limitation:** the import endpoints belong to the `students` module, so importing staff needs `students` entitled.
- **Next:** M7 (`timetable`: periods, rooms, slots with constraint-backed clash detection).

### 2026-11-26 — Session 31 (continued): Phase 7 M7
- **M6:** [PR #77](https://github.com/shafikcmt/education-erp-platform/pull/77) — CI 8/8; squash-merged pinned to `c4da30a` → **`cb9459b`** (tree identical to the head).
- **M7 (`feat/phase-07-m7`):** new `timetable` app: bell schedules and periods, rooms, weekly slots with clash detection by unique constraints plus service checks across schedules and terms; staff, teacher and portal visibility; 2 permission codes and role templates; API (plan §16.7 E40–E45).
- **Verification (local):** backend **1122 passed, 9 skipped** (4 new timetable tests); ruff, format, mypy, import-linter 9/9 and `makemigrations --check` clean; OpenAPI clean and the client regenerated; frontend `tsc` clean. GitHub CI: pending.
- **Next:** M8 (portal invitations for guardians and students; `parent_portal` shells).

### 2026-11-26 — Session 31 (continued): Phase 7 M8
- **M7:** [PR #78](https://github.com/shafikcmt/education-erp-platform/pull/78) — CI 8/8; squash-merged pinned to `8154608` → **`b1c584e`** (tree identical to the head).
- **M8 (`feat/phase-07-m8`):** portal invitations for guardians and students through the Phase 3 flow, with the login linked to the record on acceptance (new tenancy hook); relationship codes count in any scope; new `parent_portal` module with the children switcher and a child's profile, enrollment and timetable (plan §16.8 E46–E51).
- **Verification (local):** backend **1126 passed, 9 skipped** (4 new portal tests); ruff, format, mypy, import-linter 9/9 and `makemigrations --check` clean; OpenAPI clean and the client regenerated; frontend `tsc` clean. GitHub CI: pending.
- **Known gap:** guardian-visible student documents (no student document upload API or visibility flag yet).
- **Next:** M9 (frontend: students, guardians, staff, timetable, portal, imports, lifecycle, staff application entry).

### 2026-11-27 — Session 31 (continued): Phase 7 M9
- **M8:** [PR #84](https://github.com/shafikcmt/education-erp-platform/pull/84) — the first CI run failed only "images · production build + Trivy": CVE-2025-6020 (HIGH, linux-pam) in the pinned Debian base, fixed by Debian after the pin. Fixed in the same PR (`fix(docker)`): the runtime stage upgrades only the PAM packages and **fails closed** (`apt-get update --error-on=any` plus a version check; a plain update only warns, which would have hidden a no-op). Re-run CI 8/8; squash-merged pinned to `a7a0ad8` → **`58ca614`** (tree identical to the head).
- **M9 (`feat/phase-07-m9`):** frontend for Phase 7: students (list, detail, guardians, enrollment, lifecycle, documents), promotion, import wizard, staff (directory, structure, class teachers), timetable (grid, my lessons, setup), the portal, and the staff application entry (with two new staff form endpoints); en/bn strings (plan §16.9 E52–E59).
- **Verification (local):** frontend `tsc`, ESLint, Prettier and **vitest 51 passed** (2 new), `next build` clean (7 new routes); backend **1126 passed, 9 skipped** (staff form endpoints tested inside the existing admissions API test), ruff, format, mypy, import-linter 9/9 and `makemigrations --check` clean; OpenAPI clean and the client regenerated. GitHub CI: pending. E2E for these screens comes in M10.
- **Next:** M10 (E2E for the Phase 7 journeys, security self-review, docs; then Phase 7 Complete for the owner's approval).

### 2026-11-27 — Session 31 (continued): Phase 7 M10 — Phase 7 Complete
- **M9:** [PR #85](https://github.com/shafikcmt/education-erp-platform/pull/85) — CI 8/8; squash-merged pinned to `252b504` → **`ad42b55`** (tree identical to the head).
- **M10 (`feat/phase-07-m10`):** real-stack E2E `frontend/e2e/people.spec.ts` (students → guardian invitation → ID card preview → staff → timetable → CSV import with dry run → the guardian's portal); a UI defect found by it and fixed (lists not refreshed after an import); security self-review `docs/security/PHASE_07_SECURITY_REVIEW.md` (plan §16.10 E60–E64).
- **Verification (local, not GitHub CI):** the new E2E passes in the Docker stack (1.6 min). Full local E2E suite: **38 passed, 6 skipped, 1 flaky** — the Phase 6 admissions journey timed out once at the score-entry step while running in parallel with the new journey, then passed on retry (its code is unchanged in Phase 7; the same flakiness was seen once in Phase 6, PR #70). Recorded as a known gap, not fixed. Frontend tsc, ESLint, Prettier, vitest and `next build` clean.
- **Phase 7 status:** **Complete**, awaiting the owner's approval. **Phase 8 is not started** and needs the owner's approval of Phase 7 and of a Phase 8 plan.
- **Open items for the owner** (security review §3): guardian-visible student documents; staff imports need `students`; preview CSS under the page CSP; cross-schedule clashes are service-checked only; phone sign-in waits for an SMS provider.

### 2026-11-28 — Session 31 (continued): Phase 7 approved; Phase 8 plan proposed
- **M10:** [PR #86](https://github.com/shafikcmt/education-erp-platform/pull/86) — GitHub CI **8/8 success**; squash-merged pinned to `83f6198` → **`9844695`** (tree identical to the head).
- **Owner (2026-11-28):** "approval all ur recommended and continue develop same". **Phase 7 Approved**, and ADR-075 Accepted:
  - the residual risks of the Phase 7 self-review §3 are accepted as recorded;
  - the database-level guard for clashes between overlapping periods of different bell schedules moves to Phase 18 (same-period clashes stay constraint-backed).
- **Phase 8 plan proposed (`docs/phase-08-plan`):** `docs/plans/PHASE_08_PLAN.md` covers registers and records, statuses and modes as Studio settings, marking by relationship scope with optimistic concurrency, edit window and lock, staff attendance, leave requests through workflows, absence alerts and thresholds, reports and the portal, the device API design and the partition evaluation. Nine owner questions with recommendations. ADR-076 to ADR-080 are Proposed.
- **Verification:** documentation only; no code changed, so no test suite was re-run in this step.
- **CI finding fixed on the same branch:** the first CI run failed only in Trivy: CVE-2026-124851 (HIGH, `libzstd1`), fixed by Debian (`1.5.4+dfsg2-5+deb12u1`) after the base image was pinned. The backend runtime stage now upgrades `libzstd1` with the same fail-closed pattern as linux-pam (`apt-get update --error-on=any` and a version check). It could not be built locally: the Debian mirrors are blocked from this environment, so GitHub CI is the verification.
- **Next:** the owner's decision on the Phase 8 plan and Q1–Q9. No Phase 8 code is written before approval.

### 2026-11-28 — Session 31 (continued): Phase 8 plan approved; M1
- **Plan:** [PR #87](https://github.com/shafikcmt/education-erp-platform/pull/87) — GitHub CI **8/8 success** after the libzstd1 image fix; squash-merged pinned to `ae620fe` → **`138c35e`** (tree identical to the head).
- **Owner (2026-11-28):** "approval all ur recommended and continur develop same". The Phase 8 plan is **Approved** with all nine recommended answers (ADR-081); ADR-076 to ADR-080 Accepted.
- **M1 (`feat/phase-08-m1`):** `attendance` app (registers, records, staff records, leave requests) with composite keys and RLS; seven Studio settings read in one place; v3 presets (attendance mode per type, the new defaults); 8 permission codes and role templates (plan §18.1 A1–A8, with the deviations recorded there).
- **Verification (local, not GitHub CI):** backend **1132 passed, 9 skipped** (6 new attendance tests; test facts updated: 116 codes, 18 presets with v3 defaults, teacher codes, installed modules); ruff, format, mypy (435 files), import-linter 9/9, `makemigrations --check` clean; OpenAPI regenerated with no drift (no API in M1). The first full run had 2 failures, both stale facts (preset count, default preset version), fixed.
- **Next:** M2 (marking services and API: registers, roster, save with optimistic concurrency, submit, edit window, lock and unlock, audit; scope tests).

### 2026-11-28 — Session 31 (continued): Phase 8 M2
- **M1:** [PR #88](https://github.com/shafikcmt/education-erp-platform/pull/88) — GitHub CI **8/8 success**; squash-merged pinned to `900dede` → **`5113fc7`** (tree identical to the head).
- **M2 (`feat/phase-08-m2`):** marking selectors, services and API: open, roster with approved leave, save with optimistic version (409), submit, edit window with manager reason, MFA and step-up, unlock, `lock_due`; audit events; host-route review entries; OpenAPI and client regenerated (plan §18.2 A9–A14).
- **Verification (local, not GitHub CI):** backend **1138 passed, 9 skipped** (6 new marking tests; host-route review updated); attendance tests re-run after a fixture change (12 passed); ruff, format, mypy (442 files), import-linter 9/9, `makemigrations --check` clean; OpenAPI `--validate --fail-on-warn` clean (two serializer names changed to avoid a component clash) and client regenerated; frontend `tsc` clean; Prettier clean on the docs and client.
- **Next:** M3 (leave requests: workflow subject, built-in single step, pre-fill and conflicts, attachments).

### 2026-11-28 — Session 31 (continued): Phase 8 M3
- **M2:** [PR #89](https://github.com/shafikcmt/education-erp-platform/pull/89) — GitHub CI **8/8 success**; squash-merged pinned to `753d61e` → **`b750304`** (tree identical to the head).
- **M3 (`feat/phase-08-m3`):** leave requests for students and staff: request, decide, cancel; reviewers by permission combination (class teachers only for their own units); optional workflow gate (`attendance.leave_workflow`, subject `attendance.leave_request`); pre-fill through the roster; API (plan §18.3 A15–A20).
- **Known gap added:** leave attachments (A20).
- **Verification (local, not GitHub CI):** backend **1143 passed, 9 skipped** (5 new leave tests; shared attendance fixtures moved to a conftest); ruff, format, mypy (445 files), import-linter 9/9, `makemigrations --check` clean; OpenAPI `--validate --fail-on-warn` clean and client regenerated; frontend `tsc` clean; Prettier clean.
- **Next:** M4 (staff daily register and staff leave pre-fill).

### 2026-11-28 — Session 31 (continued): Phase 8 M4
- **M3:** [PR #90](https://github.com/shafikcmt/education-erp-platform/pull/90) — GitHub CI **8/8 success**; squash-merged pinned to `751dd3a` → **`69fb10e`** (tree identical to the head).
- **M4 (`feat/phase-08-m4`):** the staff daily register (campus and institution scopes, check-in and check-out, approved staff leave pre-filled, reason and step-up past the edit window), one's own days, API (plan §18.4 A21–A24).
- **Verification (local, not GitHub CI):** backend **1146 passed, 9 skipped** (3 new staff-register tests); ruff, format, mypy (447 files), import-linter 9/9, `makemigrations --check` clean; OpenAPI `--validate --fail-on-warn` clean and client regenerated; frontend `tsc` clean; Prettier clean.
- **Next:** M5 (absence alerts, the `attendance.flag` rule namespace, P29 nightly lock and flags, the promotion variable).

### 2026-11-28 — Session 31 (continued): Phase 8 M5
- **M4:** [PR #91](https://github.com/shafikcmt/education-erp-platform/pull/91) — GitHub CI **8/8 success**; squash-merged pinned to `537bdcf` → **`04962fc`** (tree identical to the head).
- **M5 (`feat/phase-08-m5`):** absence alerts once per student per day; figures and percentages; P29 nightly lock and low-attendance flags with class-teacher notices; the `attendance.flag` rule namespace; `attendance.*` variables for promotion rules (plan §18.5 A25–A29).
- **Verification (local, not GitHub CI):** backend **1152 passed, 9 skipped** (6 new alert, figure and flag tests; catalogue test now P1–P29); ruff, format, mypy (451 files), import-linter 9/9, `makemigrations --check` clean; OpenAPI unchanged (no API in M5); Prettier clean.
- **Next:** M6 (reports, CSV, the monthly register template, portal endpoints; `safe_cell` moved to core).

### 2026-11-28 — Session 31 (continued): Phase 8 M6
- **M5:** [PR #92](https://github.com/shafikcmt/education-erp-platform/pull/92) — GitHub CI **8/8 success**; squash-merged pinned to `8ccaf6a` → **`a2e8172`** (tree identical to the head).
- **M6 (`feat/phase-08-m6`):** reports (daily status, unit month, student summary, staff month) with formula-safe CSV; `safe_cell` moved to core; the monthly register template kind and document; the guardian/student attendance view (plan §18.6 A30–A33).
- **Verification (local, not GitHub CI):** backend **1157 passed, 9 skipped** (5 new report and portal tests; the import's `safe_cell` test now targets core); ruff, format, mypy (455 files), import-linter 9/9, `makemigrations --check` clean; OpenAPI `--validate --fail-on-warn` clean after renaming a colliding `DocumentSerializer`, client regenerated; frontend `tsc` clean; Prettier clean.
- **Next:** M7 (partition evaluation with generated data and query plans; the device API design document).

### 2026-11-28 — Session 31 (continued): Phase 8 M7
- **M6:** [PR #93](https://github.com/shafikcmt/education-erp-platform/pull/93) — GitHub CI **8/8 success**; squash-merged pinned to `138a6c2` → **`e53068d`** (tree identical to the head).
- **M7 (`feat/phase-08-m7`):** partition evaluation with 5 M generated rows in a throwaway database (every report query under 40 ms; no gain from partitioning; ADR-080 stands, measurements and migration path recorded); the device API design document (plan §18.7 A34–A36).
- **Verification:** the evaluation script ran to completion locally (output kept in the session scratchpad, not committed); documentation and an SQL script only, so no test suite change. Prettier on the docs.
- **Next:** M8 (frontend: teacher quick-mark on mobile, registers, staff register, leave, reports, portal attendance; en and bn).

### 2026-11-28 — Session 31 (continued): Phase 8 M8
- **M7:** [PR #94](https://github.com/shafikcmt/education-erp-platform/pull/94) — GitHub CI **8/8 success**; squash-merged pinned to `16c0fdd` → **`7632494`** (tree identical to the head).
- **M8 (`feat/phase-08-m8`):** the attendance screens (en and bn): teacher Today and the quick-mark register with conflict handling, registers, leave, staff register, reports with CSV, the portal attendance card (plan §18.8 A37–A41).
- **Verification (local, not GitHub CI):** frontend `tsc`, ESLint (whole app), Prettier (repo), vitest **55 passed** (4 new), `next build` succeeded with the `/[locale]/attendance` route. No backend change. The screens have not yet been exercised in a browser end to end: that is the M9 E2E.
- **Next:** M9 (E2E on a mobile viewport: teacher marks, guardian sees the alert and requests leave, reports; security self-review; Phase 8 Complete for the owner's approval).

## Known gaps / open questions

- **Phase 8 M3 (plan §18.3 A20):** leave requests have no attachments yet; a guardian-facing upload for leave evidence needs its own authorisation (revisit with the M8 frontend).
- **Phase 18 (ADR-075):** a database-level guard for timetable clashes between overlapping periods of different bell schedules (today service-checked only).
- **Flaky E2E step (Phase 6 admissions journey):** under parallel load the score-entry step occasionally times out (passed on retry locally and in CI before). Cause not yet identified; investigate before relying on single-run CI.

- Price points, tier boundaries, trial length (ADR-024).
- Payment gateways for SaaS billing and fee collection (ADR-017).
- Hosting provider, region, data residency (ADR-019).
- Legal/compliance review for minors' data, retention periods, VAT/tax invoicing.
- **Security-event IP retention (ADR-036):** default 365 days and lawful basis are **pending legal review before production**. Nginx access logs contain plaintext client IPs; set their retention and rotation policy in Phase 19.
- Numeric NFR targets (latency, availability, RPO/RTO) are proposed, not approved.
- **Phase 5 gaps (recorded, not hidden; plan §13):**
  - Preset content is a draft for review with real institutions (ADR-060 Q4).
  - Studio v1 edits rules, forms, workflows and templates as JSON; visual builders are not built (§13.7 C38).
  - The onboarding wizard is a dashboard checklist, not a separate flow (C40).
  - Self-service sign-up moved from M7 to M8 (C41); built in M8 with **mandatory** approval (ADR-061, Accepted 2026-11-23).
  - Custom field values on members wait for member profiles (Phase 7).
- **Phase 6 gaps (recorded, not hidden; plan §13):**
  - ~~Presigned uploads not yet exercised against the real object store from a browser~~ — **done in M8** (real-stack E2E; `FILES_UPLOAD_ORIGIN` and `S3_PUBLIC_ENDPOINT_URL` set in the E2E stack only).
  - No malware scanner yet: files stay `unscanned` and staff-only (ADR-066 Q8, Phase 18).
  - Applicants are not emailed about decisions or offers yet; they see them through the status link (Phase 14).
  - CI: the stack E2E job of PR #70 failed once (unknown test; the log host is blocked here) and passed on re-run and locally. Watch for flakiness; if it recurs, add a per-test timing report to the CI job.
  - UI gaps after M7: no staff screen to enter an application (API only; the public form works); no screens for terms and offerings (API only); Studio keys are typed in the cycle dialog (no pickers).
- **Phase 3 M5 gaps (recorded, not hidden; plan §24.8):**
  - ~~**No HTTP endpoints** for support sessions and the approval setting~~ — **resolved in M8**.
  - ~~**Suspension service (P5)**~~ — **resolved in M8** (revokes open support sessions).
  - ~~**No scheduled expiry sweep**~~ — **resolved in M7** (`tenancy.sweep_support_sessions` every 5 minutes).
  - ~~**Eager-mode Celery warning**~~ — **resolved in M7** (C6; plan §24.10 N70).
  - **K6 prefork:** K6 runs with an in-process threaded worker; the prefork run through the compose worker comes with the M10 stack tests.
- **Phase 3 M4 gaps (recorded, not hidden; plan §24.7):**
  - ~~**No HTTP API yet** for members, invitations, roles and assignments~~ — **resolved in M8**.
  - ~~**Invitation acceptance** for existing signed-in accounts only~~ — **resolved in M8** (new account, or existing account with password; plan N80).
  - ~~**Provisioning (P4)** and the platform permission codes~~ — **resolved in M8**.
  - ~~**MFA enrollment** on the platform host only~~ — **resolved in M8** (own MFA and step-up on tenant hosts, N81).
  - ~~`rbac_role` / `rbac_rolepermission` have no RLS~~ — **resolved in M6** (dual-scope RLS). The explicit `tenant_id` filters in M4 code stay as a second layer.
  - ~~**Inviter re-check:** an invitation stays valid if the inviter later loses the right to invite~~ — **resolved 2026-11-23** (ADR-062: member-created invitations are re-authorised at acceptance).
- **Phase 3 M8 gaps (recorded, not hidden; plan §24.11):**
  - ~~**No frontend** for M8 endpoints~~ — **resolved in M9** (plan §24.12).
  - Tenant lists (institutions, campuses, members, invitations) are filtered in Python after a per-object permission check: fine for Phase 3 sizes (limits 1/3), to be revisited with pagination before large tenants exist.
  - Tenant hosts stay **disabled**; production provisioning is refused until they are enabled (D1).
- **Phase 3 M9 gaps (recorded, not hidden; plan §24.12 N88):**
  - ~~**Tenant-host screens are not covered by E2E**~~ — **resolved in M10** for the main journeys (desktop, English).
- **Phase 3 M10 gaps (recorded, not hidden; plan N93):**
  - **D9 isolation-overhead benchmark not run.** It needs the §8.4 benchmark settings, a scratch database and a no-RLS control. No numbers are estimated.
  - ~~Mobile and Bengali tenant-host E2E~~ and ~~daily denial report~~ — **resolved in M10 part 2** (plan §24.14).
  - Prefork K6; Sentry alerts (no Sentry account; none is created without the owner).
  - ~~**D9 benchmark**~~ — **moved to Phase 18** by the owner (ADR-049, 2026-11-21).
  - **K4** is covered at the primitive level only (M2 test); the service-level test arrives with the institution API (M8).
- **Phase 3 M3 gaps (recorded, not hidden; `plans/PHASE_03_M3_PLAN.md` §11.4):**
  - ~~**R2** cross-tenant invisibility of audit events~~ — **resolved in M6** (private dual-scope RLS on both audit tables; `tests/isolation/test_dual_scope_tables.py`).
  - **R9** (support-session read audited atomically) is not implemented (**M5**).
  - **K3** (concurrency through Nginx/Uvicorn) is not implemented (**M10**); L9 is covered in process only.
  - ~~**External-I/O guards** (email, storage)~~ — **resolved in M7** (`apps.core.tenancy.keys`; guarded test email backend).
  - **Suspended tenants** deny everyone, owners included, and **offboarding** tenants deny all writes, until M4/M5 add owner roles and the D2 restricted mode.
  - **No tenant RBAC source** exists before M4: on a tenant host only self-service (own account) permissions work.
  - **D4 measurement** was taken on the development stack (debug server settings, shared VM), so absolute numbers are indicative only; see `docs/benchmarks/PHASE_03_CONNECTIONS.md`.
  - **Docker image rebuild** could not run in this session's sandbox (package downloads are blocked inside `docker build`). The stack ran the new code through the development bind mount with the existing images; dependencies did not change. GitHub CI builds the images.
  - **Trust assumption:** the API must be reachable only through Nginx and the web service, because Django trusts `X-Forwarded-Host` set by them (`SECURITY.md` §6a).
- **Phase 3 M2 follow-ups:**
  - N16 and N18 were decided by the owner on 2026-11-09 (plan §24.5).
  - **Phase 18 requirement:** refuse tenant reactivation once a purge has started.
  - **M5 requirement:** register `tenancy.support_session.request` and align the `platform_support` template, which currently lists `platform.support_session.request`.
  - P6 fails closed until then.
- **Phase 3 M1 follow-ups:**
  - ~~**O1:** `rbac_permission` writable by `erp_app`~~ — **resolved 2026-11-09** (Session 15). The catalogue bootstrap is owner-only, and `erp_app` has SELECT only.
  - `rbac_role`, `rbac_rolepermission`, `audit_auditevent` and `audit_auditeventip` have no RLS yet. They are registered as pending M6 in the coverage gate (plan §24.1 N6).
  - The Celery boundary leak detector can only clear and log, not fail the task (Celery signal semantics; N11).
  - `platform_scope` audit events are not yet durable; the durable audit connection comes in M3 (N12).
  - CI runs only on PRs and pushes to `main`, so the M1 branch push ran no CI. All checks were run locally (Session 14).
- **Phase 3 (planned):**
  - Tenant hosts must stay disabled in production until the owner provides the production domain and approves the Phase 3 security review (D1).
  - The D9 performance values are initial engineering targets that must be measured (plan §8.4), not guarantees.
  - Break-glass access is deferred to Phase 18 (D6).
- Institution-type preset content (especially madrasa variants and hostel profile defaults) needs validation with real institutions.
- Branch protection for `main` must be configured by the repository owner in GitHub settings (require the CI jobs listed in `DOCKER_DEPLOYMENT.md` §6).
- ESLint is held at 9.x (deprecated upstream) and TypeScript at 5.9; both are owner-approved as temporary, with upgrade triggers tracked in ADR-030.
- GitHub Actions warns that `astral-sh/setup-uv@v6` and `pnpm/action-setup@v4` run on the deprecated Node 20 runtime; bump them when Node 24 majors are available (ADR-030 tracking; Dependabot watches actions).
- ~~`erp_app` still has DML on `django_migrations`~~ — **resolved in Phase 2** (`core.0002`: SELECT only).
- **Phase 2 follow-ups:**
  - Bengali UI and email copy should be reviewed by a native-speaking editor before launch (written for natural wording, not yet reviewed).
  - Email deliverability/provider is undecided (Mailpit in dev; provider in Phase 14/19).
  - The E2E bootstrap admin (`create_platform_admin`) needs fresh volumes for a rerun (`make down` with `-v`, then `make up`).
  - The per-IP login limit (default 20 / 5 min) may be too low for institutions behind one NAT address; it is tunable (`SECURITY_LOGIN_IP_LIMIT`) and is revisited with tenant hosts in Phase 3.
  - Breached-password checking is implemented but off by default; enabling it needs outbound access to `api.pwnedpasswords.com` (ADR-037).
  - Production key management (secret manager, key backup and rotation runbook) depends on ADR-019 (Phase 19).
  - **Audit tamper evidence (ADR-040):** the owner role can still disable the audit trigger by DDL; protection rests on owner-credential isolation. Off-site/hash-chained audit storage: Phase 18.
  - **Phase 19 must keep the owner/runtime secret separation** (compose allow-lists and the startup guard exist; the production deployment is not built yet).
  - The MFA and login locks live in Redis: a cache flush clears active locks (counters restart).
  - CODEOWNERS is in place; the owner must enable "Require review from Code Owners" in branch protection.
  - Six Dependabot PRs (#3, #4, #7, #8, #9, #14) wait for a rebase onto the post-Phase-2 `main` and a fresh CI run (see Session 9).
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

### 2026-11-06 — Session 7 (PR #12 merge, Phase 2 plan rev. 3)
- **PR #12 merged by Claude under owner authorization**, after verifying every condition:
  1. open and mergeable (`clean`), with its base still `main` at `cb2383e`;
  2. 8/8 CI check runs `success` on head `9f6d7c4`;
  3. 0 reviews, 0 review threads, 0 comments, no requested reviewers;
  4. final diff reviewed: 19 files, no deletions, renames, env files or artifacts, and every security change tightens controls;
  5. squash-merged, pinned to the reviewed head SHA, with no force-push or bypass;
  6. **merge commit `d80f576554937f95c214b08a8f5d7c883ec721a9`**, whose tree is byte-identical to the reviewed head.
- **PR #13:**
  - GitHub did not retarget it automatically, because the base branch still exists.
  - After the squash merge, the docs branch still carried the original PR #12 commits, so I rebased only the 2 documentation commits onto `main` (my own branch, `--force-with-lease`) and retargeted PR #13 to `main`.
  - The diff is now 11 documentation files only.
- **Q10 approved with strict conditions → ADR-038**, amending ADR-037's Q5 line for this case only. Manual MFA key:
  - only during initial enrollment, after fresh step-up, shown once (then `410`);
  - restart setup (new secret) if lost;
  - never in logs, analytics, emails, audit or later responses;
  - secret encrypted at rest;
  - step-up allowed in the restricted enrollment session.
- **Q11 approved → ADR-039:** `@hookform/resolvers` 7.0.x with its official Zod integration, recorded in `TECH_STACK.md`.
- **Plan rev. 3:** §6.6, §8 (2 new endpoints), §9, §10, §11, §13, §15 and §16 updated. No open questions remain.
- **Phase 3 consistency:** unaffected. `MFADevice` stays a platform (user-owned) table, and the reveal endpoint is a platform/self-service endpoint.
- **No application code; no implementation branch created.**
- **Next recommended task:** owner gives final approval of Phase 1 and the Phase 2 plan, and merges PR #13. Then implement on `feat/phase-02-auth-rbac`.

### 2026-11-06 — Session 8 (Phase 2 implementation)
- **Owner approvals:** Phase 1 `Approved`; Phase 2 plan rev. 3 approved; implementation authorized (merge PR #13 first; never merge the implementation PR without approval).
- **PR #13** verified (open, `clean`, 8/8 checks green, 11 documentation files only) and **squash-merged pinned to head `20432ee`** → `main` `7d860b0`; the merged tree is identical to the reviewed head. Branch `feat/phase-02-auth-rbac` created from it.
- **Implemented** everything in plan §15 (details and 14 recorded deviations in `plans/PHASE_02_PLAN.md` §18):
  - migrations: `core.0002`, `identity.0002`, `rbac.0001`/`0002`, `audit.0001`/`0002` (all additive; no tenant-owned tables);
  - 38 API views under `/api/v1/auth/`, `/me/`, `/platform/`; OpenAPI with zero warnings; TS client regenerated;
  - frontend: login, MFA, forced enrollment (QR + one-time manual key + recovery codes), forgot/reset, activate, verify email, account security, platform users/roles/audit, step-up dialog, idle warning — en + bn;
  - dependencies installed exactly as approved: pyotp 2.10.0, cryptography 50.0.2, segno 1.6.6, @tanstack/react-query 5.106.1, react-hook-form 7.91.0, zod 4.6.7, @hookform/resolvers 7.0.3.
- **Verification (local, actual results):**
  - backend: ruff, ruff format, mypy strict (135 files), import-linter (2 contracts kept); pytest **237 passed, 9 skipped**, coverage **95%**;
  - `spectacular --validate --fail-on-warn`: 0 warnings; gitleaks (working tree and git history): no leaks;
  - frontend: ESLint, Prettier, `tsc`, Vitest **28 passed**;
  - clean-volume `docker compose up --wait`: all services healthy; `smoke_check` OK; Playwright **21 passed** (setup + desktop + mobile).
- **CI on PR #15:** first run failed only on gitleaks (a dummy test password in history) → pinned in `.gitleaksignore`, test now uses a derived constant.
- **Next recommended task:** owner reviews PR #15 (security review notes in the PR) and decides on merge; then plan Phase 3 (tenants, institutions, campuses, memberships, RLS, support sessions).

### 2026-11-06 — Session 9 (independent security review and fixes)
- **Review** of PR #15 at `a77ed9b`: 3 high, 4 medium, 6 low and 2 informational findings, confirmed with temporary probe tests and live PostgreSQL checks (owner role could disable the audit trigger; runtime containers held owner credentials).
- **Owner authorized all fixes** (L5 approved as a feature). Implemented on `feat/phase-02-auth-rbac` (ADR-040; plan §18.1):
  - backend: per-account MFA lock, network-scoped login lock, privileged-target rule in services, token invalidation, fingerprint retention, expired-session housekeeping, service-level permission checks, random cache version, IP side-table triggers (`audit.0003`), recovery-code step-up, `__Host-csrftoken`, audit rollback guard, owner-credential startup guard;
  - infrastructure: compose environment allow-lists (no `env_file`), `infra/scripts/check_runtime_secrets.py`, CI checks on config and running containers, CODEOWNERS;
  - frontend: nonce-based CSP via the Next.js proxy (pages render per request), zod jitless, step-up dialog with recovery codes, new en/bn messages;
  - architecture: 3 new import-linter contracts.
- **Verification (actual results):** backend 286 passed / 9 skipped, coverage 95%; ruff, mypy (139 files), import-linter (5 contracts kept); OpenAPI regenerated, no drift; frontend ESLint, Prettier, `tsc`, Vitest 32 passed, production build; clean-volume stack healthy, `smoke_check` OK, runtime containers hold no owner credentials; Playwright **31 passed** with zero CSP violations; gitleaks (git history and tree) clean; Trivy clean on both runtime images.
- **Dependabot review:** #3 (setup-uv 7), #4 (setup-node 7), #7 (upload-artifact 7), #8 (checkout 7), #14 (pnpm/action-setup 6) are within ADR-030 (they address the Node 20 runner deprecation) and #9 (Mailpit 1.33.0, dev only) needs the ADR-030 pin table updated. All were green on the pre-Phase-2 `main` only; rebase and re-run CI after PR #15 merges, then merge one at a time with owner approval. None was merged.
- **Next recommended task:** owner's final security review of PR #15 and merge decision; then Dependabot rebases; then the Phase 3 plan.

### 2026-11-08 — Session 10 (Phase 2 merge; Phase 3 planning, documentation only)
- **PR #15 merge (owner-authorized):** all merge conditions were verified first:
  - the PR was open and ready;
  - the head was exactly `2cf3670`;
  - all 8 checks were green;
  - there were no conflicts and no blocking comments.
  It was then squash-merged into `main` as `2d61e83`, and the merged tree is identical to the reviewed head. No branch protection or required check was bypassed, and no history was rewritten. Phase 2 is now `Approved`.
- **Phase 3 planning (documentation only), on branch `docs/phase-03-plan` from `main` `2d61e83`:**
  - `plans/PHASE_03_PLAN.md` rev. 1 (Proposed). It covers:
    - the domain model and ERD;
    - the RLS policy catalogue;
    - the tenant context lifecycle (pooling, concurrency, Celery);
    - tenant-aware RBAC and revocation;
    - host resolution and the enablement gate;
    - support sessions;
    - the API specification and frontend flows (en/bn);
    - the threat model (T1–T17) and monitoring;
    - the test strategy and the six isolation checks;
    - migration and rollback, milestones M1–M11, acceptance criteria and risks.
  - ADR-041 to ADR-046 were added to `DECISION_LOG.md` as **Proposed**. The roadmap and `CLAUDE.md` phase table were updated, with no rule changed.
- **Code inspected for the plan** (verified on `main`, no changes):
  - `ScopeTargetMiddleware` maps every host to the platform scope;
  - the dev `ALLOWED_HOSTS` contains `.localhost`;
  - `ATOMIC_REQUESTS = False` and `CONN_MAX_AGE = 60`;
  - the Problem Details handler doesn't call `set_rollback`;
  - `audit_auditeventip` has no `tenant_id`.
  The plan addresses each of these.
- **Dependencies:** none proposed.
- **No application code changed; no implementation branch created.** Dependabot PRs were not processed (owner instruction).
- **Verification:** documentation only. Prettier format check on the changed Markdown (result in the PR).
- **Next recommended task:**
  1. The owner reviews the Phase 3 plan, answers Q1–Q12 and accepts or amends ADR-041–046.
  2. Merge the documentation PR with approval.
  3. Implement on `feat/phase-03-tenancy`, milestone M1 first.

### 2026-11-08 — Session 11 (Phase 3 plan revision 2, documentation only)
- **Owner review of rev. 1:**
  - Q1–Q12 approved in principle.
  - Runtime BYPASSRLS not approved; a complete, security-reviewed replacement and a threat model are required.
  - Ten additional requirements set.
- **Plan rev. 2** (`plans/PHASE_03_PLAN.md`), with each requirement mapped to its section:
  - ADR-009 reconciliation and the `erp_platform` disposition: kept, unused, nothing removed;
  - the platform operation catalogue P1–P16, including the IP-anonymisation task affected by the new RLS;
  - a threat model for each of the three `SECURITY DEFINER` functions, which read through owner-only `SELECT` policies;
  - rollback and durable-audit matrix (R1–R9) and performance safeguards;
  - leak verification for requests and Celery (L1–L10, C1–C10) and concurrency tests (K1–K8);
  - host decision table, disabled-mode behaviour, placeholder domain, and refusing production provisioning while tenant hosts are disabled;
  - composite-only foreign keys (PostgreSQL FK checks ignore RLS) with integrity and migration tests;
  - import boundaries and new import-linter contracts;
  - support-session guarantees S1–S9;
  - registry allow-list with a justification and tests for each entry;
  - `tenancy_tenant` self-scoped.
- **Decision log:** ADR-041–046 revised (rev. 2); ADR-047 added (owner answers). All Proposed. No Accepted ADR changed.
- **Roadmap:** files module → Phase 6/7; self-service sign-up → Phase 4/5. Both take effect on final plan approval.
- **Facts verified in code for rev. 2:**
  - the production server is Gunicorn with Uvicorn workers (ASGI), and all views are sync;
  - `erp_platform` is `NOLOGIN`, `BYPASSRLS`, has no members and isn't used by any code;
  - tests run as `erp_app` with `CONN_MAX_AGE = 0`;
  - `audit.anonymize_expired_ips` iterates over all IP rows without a context;
  - sessions use `cached_db`;
  - there are 5 existing import-linter contracts.
- **No application code; PR #16 stays documentation only and is not merged.**
- **Verification:** Prettier check on the changed Markdown and a section cross-reference check (results in the PR).
- **Next recommended task:**
  1. The owner gives final approval of plan rev. 2 and ADR-041–047, and answers D1–D9 where possible (D1 can come later; it blocks only production enablement).
  2. Merge PR #16 with approval.
  3. Implement on `feat/phase-03-tenancy`, starting with M1.

### 2026-11-08 — Session 12 (Phase 3 plan revision 3, documentation only)
- **Verified before changes:**
  - PR #16 open, `clean`, head `82a5d65`, CI 8/8 green;
  - `main` at `2d61e83`;
  - no `feat/phase-03-tenancy` branch.
- **Owner review of rev. 2:** ADR-041–047 approved in principle; D1–D9 decided; final documentation requirements set.
- **Plan rev. 3** (`plans/PHASE_03_PLAN.md`):
  - D1–D9 applied throughout;
  - suspended-tenant restricted mode (§11.3, S10);
  - approval-setting rules for D5;
  - generic sign-in error (D7);
  - `CONN_MAX_AGE = 0` with a leak-test gate for any later change (D4);
  - D9 thresholds and benchmark methodology, including the environment record (§8.4);
  - approval-gate checklist mapping each final requirement to design and tests (§23);
  - §17.3 lists what is still open.
- **Decision log:**
  - ADR-041–047 marked approved in principle, with D1–D9 added to their bodies;
  - ADR-009 stays **Accepted**, with an append-only note giving the exact pending §5 wording; the original text is unchanged.
- **Roadmap, `CLAUDE.md` phase table and this tracker:** updated. No rule changed.
- **No application code; no implementation branch; PR #16 not merged.**
- **Verification:**
  - Prettier check on the changed Markdown;
  - section cross-reference check;
  - check that every relative document link resolves;
  - PR CI results (recorded in the PR and the session report).
- **Next recommended task:**
  1. Owner gives final approval.
  2. Merge PR #16 with that approval.
  3. Create `feat/phase-03-tenancy` and implement M1.

### 2026-11-08 — Session 13 (Phase 3 plan approval and merge; implementation branch)
- **PR #16 merge (owner-authorized):** all merge conditions were verified first:
  - the PR was open, `clean` and targeting `main`;
  - the head was exactly `a54d5a4`;
  - all 8 checks were green on that head;
  - there were no reviews, review threads or comments;
  - the diff was 6 documentation files only.

  The PR was then squash-merged, pinned to `a54d5a4`, as **`75bb2c5`**. The merged tree is identical to the reviewed head. No branch protection or required check was bypassed.
- **Implementation branch:** `feat/phase-03-tenancy`, created from `main` `75bb2c5` and pushed.
- **Owner final approval:**
  - plan rev. 3 **Approved**;
  - ADR-041–047 **Accepted** (including D1–D9);
  - ADR-009 stays Accepted, and the §5 amendment by ADR-043 is recorded as in effect (append-only note);
  - `CLAUDE.md` §10 item 3 updated.

  This documentation commit is the first commit on `feat/phase-03-tenancy`.
- **M1 checklist prepared** (session report): context primitives, RLS migration tooling, role restrictions, leak prevention, rollback primitives, context validation, concurrency tests K1/K2. **Not started.**
- **Stop conditions in force:**
  - no tenant hosts enabled;
  - no runtime BYPASSRLS;
  - no break-glass access;
  - no Phase 4 work;
  - no implementation PR merged without the owner's approval.
- **No application code changed.**
- **Next recommended task:** the owner authorizes M1.

### 2026-11-08 — Session 14 (Phase 3 M1: tenant context foundation)
- **Verified before coding:**
  - repository `shafikcmt/education-erp-platform`, branch `feat/phase-03-tenancy`;
  - HEAD `3778f7a`; `main` at `75bb2c5`; no uncommitted changes;
  - baseline backend suite: 286 passed, 9 skipped.
- **Implemented (owner-authorized M1 only):**
  - `apps/core/tenancy/`:
    - `TenantContext` with strict UUIDv7 validation;
    - `ContextVar` binding;
    - `tenant_atomic` (transaction-local `set_config`, savepoint nesting, conflict on a different tenant, cleanup in `finally`, alias-aware);
    - per-connection query guard;
    - `TenantScopedModel`/`TenantManager`, fail closed;
    - `platform_scope` with the P1–P16 catalogue and uncached permission/audit hooks;
    - request and Celery boundary leak detectors.
  - `apps.core.db.tenant_atomic`: a re-export under the ADR-009 name.
  - Migrations:
    - `core.0003` creates `app_tenant_id()`;
    - `core.0004` and `identity.0003` narrow framework-table grants;
    - `rbac_permission` is unchanged (O1).
  - `core.db_operations`: `EnableTenantRLS` and `EnableDualScopeRLS`, with reversal refused.
  - `tests/isolation/`:
    - RLS coverage gate with registry allow-list and meta-tests;
    - role restrictions;
    - static checks;
    - K1/K2 concurrency;
    - `platform_scope` tests.
  - Test-only probe app; second test alias.
  - Four new import-linter contracts (9 in total).
  - `01-roles.sh` comment corrected; the role itself is unchanged.
- **Verification (actual results, local):**
  - backend: **406 passed, 9 skipped**; coverage **95.02%** (gate 85%). New tenancy modules 98–100%: `context`, `models` and `boundaries` 100%, `transaction` 99%, `platform` 98%.
  - Phase 2 regression: the original 286 tests unchanged and passing.
  - ruff, ruff format, mypy (165 files): clean. import-linter: 9 contracts kept. A planted violation broke the expected contracts.
  - `makemigrations --check`: no changes. OpenAPI: no drift.
  - **RLS coverage gate:** passes, and its 11 meta-tests detect each planted violation.
  - **Role checks:** only `erp_platform` has BYPASSRLS apart from the cluster superuser; `erp_platform` is NOLOGIN with no members; the application roles inherit no privileged role.
  - **K1:** 20 threads × 50 operations. Zero cross-tenant reads or writes, and 1,000/1,000 forged cross-tenant inserts were rejected by RLS.
  - **K2:** one physical connection reused across tenants and the platform. The setting was empty between transactions, with no cross-tenant visibility.
  - **Docker stack (fresh volumes):** migrations applied as the owner; `smoke_check` OK; runtime-secret isolation OK; Playwright **31 passed**.
  - Scans: gitleaks (git history, 44 commits) found no leaks; Trivy on `uv.lock` found 0 HIGH/CRITICAL. No dependency changes.
- **Stop conditions respected:** no tenant hosts, no runtime BYPASSRLS, no break-glass, no M2+ work, no PR, nothing merged.
- **Next recommended task:**
  1. The owner reviews M1 and decides O1.
  2. On approval, start M2 (tenancy models, composite constraints, RLS, definer functions F1–F3).

### 2026-11-09 — Session 15 (Phase 3 M1 follow-up: O1, owner-controlled permission catalogue)
- **Owner decision O1:** approved with conditions — narrow `erp_app` to SELECT on `rbac_permission` after moving seeding to an owner-controlled bootstrap.
- **Implemented:**
  - `seed_roles`/`sync_permissions` run as the owner in the compose `migrate` service and in the test bootstrap;
  - both functions refuse to run as `erp_app` (code guard on top of the grant);
  - every run is audited (`rbac.permission_catalog.synced`, `rbac.system_roles.seeded`);
  - `create_platform_admin` is read-only on the catalogue: it checks with `catalog_drift()` and refuses while the catalogue is out of sync;
  - migration `rbac.0003` narrows `rbac_permission` to SELECT for `erp_app`.

  Details are in plan §24.2, and the final grant design in plan §24.3.
- **Tests:** `tests/test_permission_catalog.py` (7 tests).
  - PostgreSQL grants: SELECT only; INSERT, UPDATE, DELETE and ORM updates all refused.
  - Seeding refused as `erp_app`, with nothing written.
  - Drift detection.
  - Compose bootstrap order, and no owner URL in runtime services.
  - Repeatable and idempotent owner bootstrap on a throwaway database, using the real commands.
- Two Phase 2 tests no longer write the catalogue as `erp_app`; their seeding and deprecation checks moved into the owner-run test.
- **Verification (actual results):**
  - backend: **413 passed, 9 skipped**; coverage **95%** (gate 85%); ruff, ruff format and mypy (166 files) clean; import-linter 9/9 kept; `makemigrations --check` clean.
  - **Clean-volume Docker stack:**
    - `migrate` applied `rbac.0003`, then seeded 20 permissions and 22 roles as the owner, writing 1 audit event per step;
    - re-running `migrate` was idempotent (0 created/updated/deprecated, 0 roles created, 0 permissions added or removed);
    - `erp_app` grants on `rbac_permission`: SELECT only;
    - `seed_roles` run in the `api` container was refused;
    - `create_platform_admin` (`api`, `erp_app`) created the E2E admin;
    - Playwright **31 passed**; `smoke_check` OK; runtime-secret isolation OK.
  - Scans: see the session report (gitleaks, Trivy).
- **Next recommended task:** the owner reviews the M1 + O1 result and authorizes M2.

### 2026-11-09 — Session 16 (Phase 3: M1 merge; M2 tenancy data model)
- **M1 merge (owner-authorized):** all merge conditions were verified first:
  - PR #17 open, targeting `main`;
  - head exactly `b2ab5fa`;
  - 8/8 checks green;
  - no reviews, review threads or comments;
  - `clean`, with the working tree clean.

  It was then squash-merged, pinned to the head, as **`3108824`**. The tree is identical to the reviewed head.
- **M2 branch:** `feat/phase-03-m2`, created from `main` `3108824`.
- **Implemented (approved M2 scope only):**
  - `apps.tenancy`, with Tenant, TenantDomain, Institution, Campus, Membership, Invitation and SupportSession;
  - `TenantScopedModel.tenant` is now a registry FK;
  - migrations `tenancy.0001`–`0004` and `rbac.0004`:
    - composite FKs;
    - registry guard trigger and tombstone grant;
    - standard RLS on the six tenant tables and the self-scoped registry;
    - definer functions F1–F3 with owner-only SELECT policies;
  - slug rules, lifecycle and limits;
  - definer wrappers;
  - the test probe FK migration.

  Notes N14–N24 are in plan §24.4.
- **Verification (actual results, local):**
  - backend: **512 passed, 9 skipped**; coverage **95.37%** (gate 85%); new tenancy modules 95–100%; ruff, ruff format and mypy (181 files) clean; import-linter 9/9 kept; `makemigrations --check` clean; OpenAPI: no drift.
  - RLS coverage gate green with the new tables registered: self-scoped registry, two justified global unique keys, three approved definer functions, three owner-only SELECT policies.
  - **§4.4:** composite keys present with the expected shape. Cross-tenant and cross-institution references and template roles are rejected with `23503` for `erp_app` and the owner, and the same error is returned for a foreign id and a random id.
  - **§7:** F1–F3 threat-model tests (uniform results, columns, no PUBLIC, pinned `search_path`, hijack attempt, owner-only policies invisible to `erp_app`, single wrapper caller).
  - Raw-SQL isolation for all six tenant tables as `erp_app`.
  - Two-transaction race at the institution limit: exactly one created.
  - **Migration rehearsal:** reversal refused by default; with the override, reverse and forward work with Phase 2 data identical.
  - **Docker clean volumes:** all migrations applied as the owner; seeding as the owner; RLS forced on all seven tenancy tables; `smoke_check` OK; runtime-secret isolation OK; Playwright **31 passed**.
  - Scans: see the session report.
- **Not started:** M3 (host resolution middleware, `TENANT_HOSTS_ENABLED`) and everything later. No PR created.
- **Next recommended task:** the owner reviews M2 and decides on the M2 PR and M3.

### 2026-11-09 — Session 17 (Phase 3 M2 review decisions)
- **Owner decisions** (plan §24.5):
  - N14 accepted as implemented;
  - N16: `offboarding → active` removed; `offboarding → suspended` added; `suspended → active` is the only reactivation path;
  - N18: 35 reserved slugs added (68 in total);
  - P6: canonical code `tenancy.support_session.request`, deferred to M5.
- **Changes on `feat/phase-03-m2`:**
  - `apps/tenancy/rules.py` (transitions, reserved list);
  - the `tenancy.0002` trigger;
  - `tenancy.0001` regenerated: only the reserved list in the CHECK changed, and no follow-up migration was added;
  - new tests: the exact 68-name set, every new name refused in Python and by the database CHECK, `offboarding → active` refused in Python and SQL, `offboarding → suspended → active` allowed. The Python/SQL parity test still covers every status pair.
- **Verification (actual results, local):**
  - backend: **613 passed, 9 skipped**; coverage **95.37%**; ruff, ruff format and mypy (181 files) clean; import-linter 9/9; `makemigrations --check` clean.
  - Docker clean-volume bootstrap, smoke and Playwright, plus gitleaks and Trivy: see the session report.
- **No M3 work, no PR, no merge.**
- **Next recommended task:** the owner decides on the M2 PR.

### 2026-11-09 — Session 18 (Phase 3 M2 PR and merge)
- **PR:** [#18](https://github.com/shafikcmt/education-erp-platform/pull/18) "Phase 3 M2: Tenant Data Model and Isolation", from `feat/phase-03-m2` (head `fc544c3`).
- **Pre-PR checks:** branch based on `main` `3108824`; clean tree, remote in sync; 37 files; N14/N16/N18/P6 verified in code; migration chain `rbac.0004` → `tenancy.0001`–`0004` (probe `0002` depends on `tenancy.0001`); no M3 markers.
- **GitHub CI on `fc544c3`: 8/8 success** (backend tests as `erp_app`; backend lint/format/types/import contracts; dependency audit; frontend lint/format/types/unit tests; OpenAPI drift; production images + Trivy; gitleaks; docker compose stack + smoke + Playwright). No fixes were needed.
- **Merge:** owner authorized; squash-merged pinned to `fc544c3` → **`3616778`** on `main`. The merged tree is identical to `fc544c3`. No reviews were outstanding.
- **Carried forward:** M5 aligns `role_templates.py:36` to `tenancy.support_session.request`; M4's RoleAssignment migration is `rbac.0005` (not plan §19.1's "rbac.0003"); Phase 18 purge only for `deleted` tenants.
- **No M3 work.** Dependabot PRs untouched.
- **Next recommended task:** the owner authorizes M3 (host resolution, `TENANT_HOSTS_ENABLED` still off by default).

### 2026-11-09 — Session 19 (docs sync; Phase 3 M3 planning)
- **Docs sync:** [PR #19](https://github.com/shafikcmt/education-erp-platform/pull/19) (documentation only, 3 files) squash-merged as `e23ba29`; CI 9/9 success. `main` now contains M1 (`3108824`), M2 (`3616778`) and the status updates.
- **M3 plan (Proposed):** `docs/plans/PHASE_03_M3_PLAN.md` on branch `docs/phase-03-m3-plan`. Covers host policy, tenant resolution and transaction middleware, durable-audit alias, `TENANT_HOSTS_ENABLED` gate and production guard, tenant-host sign-in (D7), `CONN_MAX_AGE = 0` and its measurement (D4), retirement of `ScopeTargetMiddleware`. Seven questions (Q1–Q7) await the owner.
- **Known gaps recorded for later milestones:** R2 cross-tenant invisibility (M6), R9 (M5), K3 full stack (M10), storage-I/O guard (M7), owner restricted mode for suspended tenants (M4/M5).
- **No M3 implementation, no application code, no PR for the plan.**
- **Next recommended task:** the owner reviews the M3 plan and answers Q1–Q7.

### 2026-11-13 — Session 20 (Phase 3 M3 implementation)
- **Authorization:** the owner answered the seven M3 questions (ADR-048) and authorized M3 on a dedicated branch (no PR, no merge, tenant hosts stay disabled).
- **Branch:** `feat/phase-03-m3`, created from `docs/phase-03-m3-plan` (`2ea2dc0`, on top of `main` `e23ba29`).
- **Implemented (M3 scope only):**
  - host policy (`apps/tenancy/hosts.py`) and `HostPolicyMiddleware` before sessions;
  - `TenantResolutionMiddleware` (F1, session-host binding, scope) — `ScopeTargetMiddleware` removed;
  - `TenantTransactionMiddleware` (one tenant transaction, `lock_timeout = 5s`, rollback for status ≥ 400, streaming refused, `tx_ms` log and 2 s warning, host classes, membership and tenant-status gate);
  - tenant-host sign-in with the generic error (D7) through `IDENTITY_SIGN_IN_GUARDS`;
  - durable audit alias `audit_durable`, `DURABLE_ACTIONS`, `tenancy.isolation.blocked`;
  - settings and production guards (`PLATFORM_HOSTS`, `TENANT_BASE_DOMAIN`, `TENANT_HOSTS_ENABLED=false`, `CONN_MAX_AGE = 0`);
  - `infra/scripts/measure_db_connections.py` and the recorded D4 measurement.
- **Migrations:** none. No new dependency, grant, role or `SECURITY DEFINER` function.
- **Verification (actual results, local; GitHub CI has not run because no PR is open):**
  - backend: **745 passed, 9 skipped**; coverage **95.58%** (gate 85%); ruff, ruff format and mypy (192 files) clean; import-linter 9/9; `makemigrations --check` clean; OpenAPI schema unchanged.
  - frontend (unchanged code): ESLint and `tsc` clean; Vitest **32 passed**.
  - Docker: clean-volume bootstrap (migrations and seeding as the owner), `smoke_check` passed, no owner credentials in runtime containers, `*.localhost` hosts now receive the uniform 404; Playwright **31 passed**. The images themselves were **not rebuilt** (see Known gaps).
  - gitleaks: no leaks in 71 commits. Trivy on `uv.lock`: 0 HIGH/CRITICAL. Image scans were not run (no rebuilt images).
  - migration reversal rehearsal: unchanged and passing (`tests/test_tenancy_migrations.py`); M3 adds no migration.
- **D4 measurement:** `docs/benchmarks/PHASE_03_CONNECTIONS.md`. `CONN_MAX_AGE = 0` served all 18,000 measured requests; the `60` control exhausted PostgreSQL connections under concurrency (HTTP 500 for 13% of requests at concurrency 8 and 60% at 32). Cost of `0` at concurrency 1: p50 +3.2%, p95 +2.1%.
- **Not done:** M4 and later; no PR; nothing merged; nothing deployed; tenant hosts not enabled; Dependabot PRs untouched.
- **Next recommended task:** the owner reviews `feat/phase-03-m3` and decides on the M3 PR and on M4.

### 2026-11-16 — Session 21 (Phase 3 M4 implementation)
- **Authorization:** the owner asked to continue with the next tasks in the same working mode, then asked to commit only and push everything together later.
- **Branch:** `feat/phase-03-m4`, created from `feat/phase-03-m3` (`657d093`). Commits are local only.
- **Implemented (M4 scope only):**
  - `rbac.0005_roleassignment`: `RoleAssignment` (tenant-owned, RLS, composite keys), `rbac_role.template_id` with a template-only trigger;
  - 17 new permission codes (37 in total) and the administrative role templates of plan §12.3;
  - tenant system role copies, cloning and platform operation P7 (`sync_tenant_roles`, run in the `migrate` step);
  - `TenantMembershipSource` and per-tenant permission cache versions;
  - services with guard rails: grant/revoke assignments, suspend/reactivate/remove members, invitations (create, resend, revoke, accept);
  - the MFA enrollment gate and sign-in status respect the tenant scope.
- **Migrations:** `rbac.0005_roleassignment`. No new dependency.
- **Verification (actual results, local; GitHub CI has not run):**
  - backend: **801 passed, 9 skipped**; coverage **95.63%**; ruff, ruff format and mypy (209 files) clean; import-linter 9/9; `makemigrations --check` clean; OpenAPI schema unchanged (no new endpoints);
  - migration rehearsal (forward, refused reverse, allowed reverse, forward) passing with the new migration;
  - Docker clean-volume bootstrap with `rbac.0005` and `sync_tenant_roles`; `smoke_check` passed; runtime-secret isolation OK; Playwright **31 passed**; images not rebuilt (sandbox limitation, as in Session 20);
  - gitleaks: no leaks. No dependency changed since the Trivy scan of Session 20.
- **Not done:** M5 and later; no PR; nothing pushed, merged or deployed; tenant hosts not enabled; Dependabot PRs untouched.
- **Next recommended task:** the owner reviews M3 and M4, decides on pushing and the PRs, and on M5.

### 2026-11-17 — Session 22 (M3 and M4 pull requests)
- **Authorization:** the owner asked to push and merge.
- **M3:** [PR #29](https://github.com/shafikcmt/education-erp-platform/pull/29). First CI run: 7 of 8 checks passed; `backend · tests` failed on one Phase 2 test, `test_mfa_login_flow_replay_window_and_attempt_limit`. Root cause: the test asked the clock twice for "the same" TOTP step and the run crossed a 30-second boundary (05:50:59.97 UTC), so the second code was a fresh valid one. It was not an M3 defect and no security check was weakened: the test now replays the code it actually submitted (`93c4598`). Second run: **8/8 success**. Squash-merged pinned to `93c4598` → **`066b727`**.
- **M4:** rebased onto the new `main` (content unchanged) and opened as its own pull request.
- **Tenant hosts not enabled; nothing deployed; Dependabot PRs untouched.**

### 2026-11-18 — Session 23 (M4 merge; Phase 3 M5 implementation)
- **M4:** [PR #30](https://github.com/shafikcmt/education-erp-platform/pull/30) — CI **8/8 success**; squash-merged pinned to `6c58b3a` → **`14a54d6`**.
- **M5 branch:** `feat/phase-03-m5` from `main` `14a54d6`. The owner asked to continue with the next tasks in the same mode.
- **Implemented (M5 scope only):**
  - `rbac.0006` (`support_readable`), `tenancy.0005` (`duration_minutes`); 4 new codes (41 in total); `platform_support` aligned to `tenancy.support_session.request`;
  - `SupportSessionSource` (read-only, support-readable codes, host tenant only, never while suspended);
  - request gate: support mode, read-only refusal, expiry, restricted owner mode (D2); sign-in guard for staff and suspended tenants;
  - `support.request` audited in the request transaction (R9); durable `support.write_rejected` and `support.access_denied`;
  - services: request/end (P6), approve/reject/revoke, revoke on suspension, expiry, D5 approval setting; owner emails (en, bn); banner and history selectors.
- **Verification (actual results, local):**
  - backend: **815 passed, 9 skipped**; coverage **95.60%**; ruff, ruff format, mypy (213 files) clean; import-linter 9/9; `makemigrations --check` clean; OpenAPI unchanged;
  - Docker clean-volume bootstrap with the two new migrations (41 permissions seeded), `smoke_check` passed, runtime-secret isolation OK; Playwright **31 passed**; gitleaks: no leaks; no dependency change.
- **Not done:** M6 and later; tenant hosts not enabled; nothing deployed; Dependabot PRs untouched.
- **Next recommended task:** M6 (dual-scope RLS on `rbac_role`, `rbac_rolepermission` and the audit tables; tenant audit writes; P10 rewrite), which also completes the R2 invisibility test.

### 2026-11-18 — Session 24 (M5 merge; Phase 3 M6 implementation)
- **M5:** [PR #31](https://github.com/shafikcmt/education-erp-platform/pull/31) — CI **8/8 success**; squash-merged pinned to `09d9bd5` → **`cd5d07a`**.
- **M6 branch:** `feat/phase-03-m6` from `main` `cd5d07a`; owner asked to continue with M6 in the same mode.
- **Implemented (M6 scope only):**
  - `rbac.0007_dual_scope_rls`: dual-scope RLS on `rbac_role`, `rbac_rolepermission`;
  - `audit.0004_tenant_scope`: `audit_auditeventip.tenant_id` (trigger-copied, frozen, backfilled) and private dual-scope RLS on both audit tables (D3);
  - per-scope iteration under `platform_scope` (`apps/tenancy/iteration.py`); P10 retention task moved to `apps/tenancy/tasks.py` (same name and schedule); erasure, key rotation and index rebuild in every scope (P13);
  - coverage gate: no table pending RLS any more.
- **Verification (actual results, local):**
  - backend: **822 passed, 9 skipped**; coverage **95.51%**; ruff, ruff format, mypy (215 files) clean; import-linter 9/9; `makemigrations --check` clean; OpenAPI unchanged;
  - Docker clean-volume bootstrap with both migrations; seeding as the owner under RLS (22 roles, 41 permissions); `smoke_check` passed; the worker registers `audit.anonymize_expired_ips` from its new module; Playwright **31 passed**; gitleaks: no leaks; no dependency change.
- **Not done:** M7 and later; tenant hosts not enabled; nothing deployed; Dependabot PRs untouched.
- **Next recommended task:** M7 (`TenantTask`, `@platform_task` declarations, leak detectors, cache and storage key helpers; also the support-session expiry sweep and the external-I/O guards).

### 2026-11-18 — Session 25 (M6 merge; Phase 3 M7 implementation)
- **M6:** [PR #32](https://github.com/shafikcmt/education-erp-platform/pull/32) — CI **8/8 success**; squash-merged pinned to `b42e6c4` → **`0b39b39`**.
- **M7 branch:** `feat/phase-03-m7` from `main` `0b39b39`; owner asked to continue in the same mode.
- **Implemented (M7 scope only):** declared platform/tenant tasks (C10); `TenantTask` (C1–C4, C7, C9); commit-hook isolation and eager-aware leak detectors (C6); platform tasks never see a tenant (C8); support-session expiry sweep; tenant cache and storage key helpers with a static check; external-I/O guard and guarded test email backend.
- **Verification (actual results, local):**
  - backend: **841 passed, 9 skipped**; coverage **95.58%**; ruff, ruff format, mypy (222 files) clean; import-linter 9/9; `makemigrations --check` clean (no migration); OpenAPI unchanged;
  - Docker clean-volume bootstrap; the worker registers all six declared tasks and ran the support sweep end to end; `smoke_check` passed; Playwright **31 passed**; gitleaks: no leaks; no dependency change.
- **Not done:** M8 and later; tenant hosts not enabled; nothing deployed; Dependabot PRs untouched.
- **Next recommended task:** M8 (tenant-host and platform APIs, provisioning P4, suspension P5, OpenAPI and TypeScript client, URL audit with host metadata).

### 2026-11-19 — Session 26 (M7 merge; Phase 3 M8 implementation)
- **M7:** [PR #33](https://github.com/shafikcmt/education-erp-platform/pull/33) — CI **8/8 success**; squash-merged pinned to `dce992f` → **`4fbcbcc`**.
- **M8 branch:** `feat/phase-03-m8` from `main` `4fbcbcc`; owner asked to continue with the pending tasks.
- **Implemented (M8 scope only):** platform-host APIs (P2, P4, P5, P6, P8) with catalogue declarations; tenant-host APIs of plan §12.1; provisioning with compensation; suspension/reactivation revoking support sessions; audited limit overrides; invitation acceptance over HTTP (new or existing account); tenant custom-role editing; own step-up and MFA enrolment on tenant hosts; 5 platform permission codes; reviewed route lists; catalogue completeness test; OpenAPI and TypeScript client.
- **Verification (actual results, local):**
  - backend: **872 passed, 9 skipped**; coverage **96%**; ruff, ruff format, mypy (233 files) clean; import-linter 9/9; `makemigrations --check` clean (no migration); OpenAPI generated with `--fail-on-warn` (0 warnings) and committed with the TypeScript client; frontend `tsc` and ESLint clean;
  - Docker clean-volume bootstrap (migrate seeded 5 new permissions), `smoke_check` passed; Playwright **31 passed** (run with the pre-installed Chromium through `PLAYWRIGHT_CHROMIUM_EXECUTABLE`, because the container's browser build differs from the pinned Playwright's); gitleaks on the changed files: no leaks. No dependency change.
- **Not done:** M9–M11; tenant hosts not enabled; nothing deployed; Dependabot PRs untouched.
- **Next recommended task:** M9 (frontend screens of plan §13 in English and Bengali).

### 2026-11-19 — Session 27 (M8 merge; Phase 3 M9 implementation)
- **M8:** [PR #34](https://github.com/shafikcmt/education-erp-platform/pull/34) — CI **8/8 success**; squash-merged pinned to `42628fe` → **`92fcd05`**.
- **M9 branch:** `feat/phase-03-m9` from `main` `92fcd05`.
- **Implemented (M9 scope):** host-aware app shell and dashboard with a scope switcher; tenant-branded auth pages (name, safe primary colour); platform screens (My organisations, tenant registry, provisioning wizard, tenant detail with suspension, limits and owner invitation, own support sessions); tenant screens (institutions and campuses, members, invitations and assignments with a scope picker, roles, settings with the D5 approval, support access, audit log, support banner); invitation acceptance page; en + bn messages; host-guarded route groups.
- **Fix found by E2E:** empty `country` was refused by the provisioning and registry serializers (N89).
- **Verification (actual results, local):**
  - frontend: `tsc`, ESLint, Prettier clean; Vitest **38 passed** (13 files, incl. message parity and the new context helpers); `next build` succeeded;
  - backend: **872 passed, 9 skipped**; ruff, format, mypy (233 files) clean; OpenAPI regenerated (0 warnings);
  - Docker clean-volume stack with the web service running the **locally built** frontend (bind-mounted standalone output: the sandbox can't rebuild images); Playwright **33 passed** (new: provisioning wizard, registry, limit override with step-up, My organisations, tenant routes 404 on the platform host; desktop and mobile).
- **Not done:** M10–M11; tenant hosts not enabled; nothing deployed.
- **Next recommended task:** M10 (shared isolation suite, two-tenant E2E with tenant hosts in the stack, K3, isolation-overhead benchmark, threat-model test mapping).

### 2026-11-19 — Session 28 (M9 merge; Phase 3 M10, partial)
- **M9:** [PR #35](https://github.com/shafikcmt/education-erp-platform/pull/35) — CI **8/8 success**; squash-merged pinned to `c8b80b6` → **`8b19e76`**.
- **M10 branch:** `feat/phase-03-m10` from `main` `8b19e76`.
- **Implemented:**
  - two-tenant E2E on `*.localhost`; tenant hosts are enabled only in the CI/E2E stack's `.env`;
  - K3 through Nginx and Uvicorn;
  - fix: the tenant-host MFA requirement now counts every scope (N92);
  - CI enables tenant hosts and the tenant CSRF origin for its throwaway stack;
  - evidence document for the threat model and the §23 checklist.
- **Verification (actual results, local):**
  - backend **874 passed, 9 skipped**; ruff, format and mypy clean; import-linter 9/9;
  - Playwright **34 passed, 1 skipped** (the two-tenant journey runs on desktop only). The stack had tenant hosts on and served the locally built frontend through a bind mount.
- **Status:** M10 **Partial** (see gaps). M11 not started. Tenant hosts stay disabled in every committed default; nothing deployed.
- **Owner input needed:** whether the D9 benchmark must run before Phase 3 sign-off, or may move to Phase 18 with the production environment, where absolute numbers mean something.

### 2026-11-21 — Session 29 (M10 part 1 merged; M10 part 2)
- **M10 part 1:** [PR #36](https://github.com/shafikcmt/education-erp-platform/pull/36) — CI **8/8 success**; squash-merged pinned to `9b349f9` → **`e3c89da`**.
- **M10 part 2 (`feat/phase-03-m10b`):**
  - daily isolation denial report (P14);
  - Bengali owner journey on mobile in the tenant-host E2E;
  - fix: unknown hosts now get a 404 from the frontend too (N97);
  - CI E2E stack per-IP sign-in limit (N98).
- **Verification (actual results, local):**
  - backend **876 passed, 9 skipped**; ruff, format and mypy (234 files) clean;
  - frontend `tsc`, ESLint and Prettier clean; Vitest 38 passed; `next build` OK;
  - Playwright **35 passed, 2 skipped** (the two-tenant journey runs on desktop, the Bengali journey on mobile). Tenant hosts were on in the stack, which served the locally built frontend.
- **Open:** D9 benchmark (owner decision), prefork K6, Sentry alerts. Next: M11 (docs, security self-review, Phase 3 PR for owner approval).

### 2026-11-21 — Session 29 (continued): Phase 3 M11
- Documentation brought in line with what is built (database design, ERD, security §6b, deployment §5, multi-tenant §3.8); security self-review `docs/security/PHASE_03_SECURITY_REVIEW.md`.
- **Phase 3 status:** all milestones implemented. Exit criterion 11 is open only for the D9 benchmark report. **Owner decisions needed:**
  1. D9 benchmark before sign-off, or in Phase 18;
  2. approval of Phase 3 (and of the M11 PR);
  3. later, the production domain plus the security review before tenant hosts are enabled.
- Phase 4 does **not** start without the owner's approval.

### 2026-11-21 — Session 29 (continued): owner decision
- The owner accepted the recommendation: the D9 benchmark moves to Phase 18 (**ADR-049**). Phase 3 exit criteria are met → **Phase 3: Complete** (not yet *Approved*).
- Open items carried forward:
  - **Phase 18:** D9 benchmark, prefork K6, Sentry alerting (needs an account), pagination of tenant lists;
  - **owner decision:** inviter re-check at acceptance (hardening);
  - **production enablement of tenant hosts:** domain plus approved security review (D1).
- Next: the Phase 4 plan (module registry and feature entitlement engine) as **Proposed**. Implementation waits for the owner's approval.

### 2026-11-21 — Session 29 (continued): Phase 3 M11 merged; Phase 4 plan proposed
- **M11:** [PR #42](https://github.com/shafikcmt/education-erp-platform/pull/42) — CI **8/8 success**; squash-merged pinned to `559558c` → **`6665b65`**, on the owner's instruction ("continue develop with ur recommendation"). **Phase 3: Complete**; explicit owner *approval* of the phase is still to be recorded.
- **Phase 4 plan:** `docs/plans/PHASE_04_PLAN.md` (**Proposed**) with ADR-050 to ADR-053 (Proposed) and five owner questions. No Phase 4 code is written before approval.

### 2026-11-21 — Owner approval
- **Phase 3: Approved** (owner, 2026-11-21: "approved and continue develop same").
- **Phase 4 plan: Approved** with the recommended answers (ADR-054). ADR-050 to ADR-053 Accepted. Phase 4 is **In progress**; M1 starts next.

### 2026-11-21 — Session 30 (Phase 4 M1)
- **Phase 4 plan:** [PR #43](https://github.com/shafikcmt/education-erp-platform/pull/43) merged (`b73ca76`); Phase 3 Approved.
- **M1 (`feat/phase-04-m1`):**
  - `module_registry` app; the module catalogue model is SELECT-only for the runtime role;
  - `MODULE` manifests in the installed apps;
  - planned-module catalogue (34 modules in total);
  - validation (cycles, dependencies, categories);
  - owner-only audited `sync_modules`, wired into the migrate step and the test bootstrap.
- **Verification (local):**
  - backend **887 passed, 9 skipped**; ruff, format and mypy (247 files) clean; import-linter 9/9; `makemigrations --check` clean; OpenAPI unchanged;
  - `docker compose run --rm migrate` synced 34 modules.
- **Next:** M2 (billing data model with RLS classes, catalogue P17–P20).

### 2026-11-21 — Session 30 (continued): Phase 4 M2
- **M1:** [PR #44](https://github.com/shafikcmt/education-erp-platform/pull/44) — CI **8/8 success**; squash-merged pinned to `99000ed` → **`10d3365`**.
- **M2 (`feat/phase-04-m2`):**
  - billing data model; overrides and feature flags;
  - self-scoped, tenant-read-only RLS on subscriptions, items and overrides;
  - catalogue P17–P20 with uncached permission checks and both logs;
  - prices never seeded or edited; data-only flag evaluation; 7 new permission codes.
- **Verification (local):**
  - backend **893 passed, 9 skipped**; mypy (255 files) clean; import-linter 9/9; migrations check clean; OpenAPI unchanged;
  - `docker compose run --rm migrate` applied the new migrations and synced permissions and roles.
- **Next:** M3 (entitlement resolution, snapshot, cache, expiry sweep, limits from the plan, trial at provisioning).

### 2026-11-21 — Session 30 (continued): Phase 4 M3
- **M2:** [PR #45](https://github.com/shafikcmt/education-erp-platform/pull/45) — CI **8/8 success**; squash-merged pinned to `99fa5c3` → **`e1465f5`** (tree identical to the head).
- **M3 (`feat/phase-04-m3`):**
  - entitlement resolution with dependency closure, `not_built` / `missing_dependency` / `revoked`; snapshot table with standard tenant RLS; versioned cache; `require_module()` → `403 module_not_entitled`;
  - P19 hourly expiry sweep (trials, add-ons, overrides) with per-tenant recompute tasks;
  - limits from the plan with the ADR-010 override on top (settings hook, no tenancy → billing import);
  - trial plan at provisioning only when the owner has created a `trial` plan with `trial_days` (new nullable field).
  - Fix found by the tests: the cached reader counted unbuilt platform modules as enabled; it now agrees with the resolver.
- **Verification (local):**
  - backend **905 passed, 9 skipped** (12 new tests); ruff and format clean; mypy (228 files) clean; import-linter 9/9; `makemigrations --check` clean; OpenAPI unchanged;
  - `docker compose run --rm migrate` applied `billing.0003`, `module_registry.0005`/`0006`; 34 modules in sync.
- **Next:** M4 (`ModuleEntitled` permission class, URL audit `module_code`).

### 2026-11-21 — Session 30 (continued): Phase 4 M4
- **M3:** [PR #46](https://github.com/shafikcmt/education-erp-platform/pull/46) — CI **8/8 success**; squash-merged pinned to `b45202e` → **`3a7e6a5`** (tree identical to the head).
- **M4 (`feat/phase-04-m4`):**
  - `ModuleEntitled` permission class, checked before the permission; `403 module_not_entitled`; durable, aggregated denial audit;
  - `ModuleGatedView` on `TenantView`; `module_code` on every tenant-reachable view;
  - URL audit: every tenant-reachable view declares an installed module, and non-platform modules must be enforced;
  - `tenant_task(module=…)` refuses tasks of modules the tenant lacks.
- **Verification (local):**
  - backend **913 passed, 9 skipped** (8 new tests); ruff and format clean; mypy (231 files) clean; import-linter 9/9; `makemigrations --check` clean; OpenAPI unchanged (`--validate --fail-on-warn`);
  - no migrations in M4.
- **Next:** M5 (platform and tenant APIs, entitlements in `/me/context/`, OpenAPI and client).

### 2026-11-21 — Session 30 (continued): Phase 4 M5
- **M4:** [PR #47](https://github.com/shafikcmt/education-erp-platform/pull/47) — CI **8/8 success**; squash-merged pinned to `ff8b1d2` → **`d97634f`** (tree identical to the head).
- **M5 (`feat/phase-04-m5`):**
  - platform catalogue API (modules, feature flags, plans, add-ons, prices; P17) and tenant subscription API (plan, trial, add-ons, overrides; P18);
  - tenant `GET /tenant/subscription/` and `entitlements` in `/me/context/`;
  - OpenAPI regenerated (0 warnings) and TypeScript client regenerated; completeness and host-route review lists updated (restricted owner mode list unchanged).
- **Verification (local):**
  - backend **918 passed, 9 skipped** (6 new API tests plus updated gates); ruff and format clean; mypy (239 files) clean; import-linter 9/9; `makemigrations --check` clean;
  - frontend `tsc` clean, Vitest 38/38; local Playwright not run (no frontend change in M5; the CI stack job runs it).
- **Next:** M6 (frontend: platform plan management, tenant subscription panel and page, entitlement-driven navigation, en + bn).

### 2026-11-21 — Session 30 (continued): Phase 4 M6
- **M5:** [PR #48](https://github.com/shafikcmt/education-erp-platform/pull/48) — CI **8/8 success**; squash-merged pinned to `783e83a` → **`aa4b8f6`** (tree identical to the head).
- **M6 (`feat/phase-04-m6`):** entitlement-driven tenant navigation; tenant Subscription page; platform Plans and pricing page; Subscription panel on the platform tenant page; en + bn; `module_not_entitled` message.
- **Verification (local):**
  - frontend `tsc`, ESLint and Prettier clean; Vitest **40/40** (2 new);
  - full stack with the locally built frontend (tenant hosts on `*.localhost`, throwaway `.env` as in CI): Playwright **35 passed, 2 skipped** (existing suite, no regression). New Phase 4 journeys are M7.
- **Known gap:** module names are shown as codes (no `name_i18n` on modules yet).
- **Next:** M7 (Phase 4 E2E journeys, docs, security self-review, Phase 4 completion PR).

### 2026-11-21/22 — Session 30 (continued): Phase 4 M7 — Phase 4 Complete
- **M6:** [PR #49](https://github.com/shafikcmt/education-erp-platform/pull/49) — CI **8/8 success**; squash-merged pinned to `80c9955` → **`f8c924b`** (tree identical to the head).
- **M7 (`feat/phase-04-m7`):**
  - E2E journey `e2e/billing.spec.ts` (plan → test price with step-up → organisation → subscription panel → owner's Subscription page); shared steps in `e2e/tenant-flows.ts`;
  - concurrency test of subscription changes; it found a real race (F2: concurrent snapshot rewrite), fixed with a per-tenant advisory lock in `recompute()`;
  - `billing_usagerecord` with daily per-tenant metering (institutions, campuses; P19 system iteration);
  - `terminology` placeholder in `/me/context/` (empty until Phase 5);
  - security self-review `docs/security/PHASE_04_SECURITY_REVIEW.md`.
- **Verification (local):**
  - backend **921 passed, 9 skipped** before the last test fix, then the concurrency test re-run 3×; ruff, format, mypy (242 files), import-linter 9/9, `makemigrations --check`, OpenAPI `--validate --fail-on-warn` clean; client regenerated;
  - frontend `tsc`, ESLint, Prettier clean; Vitest 40/40;
  - full stack rebuilt with the M7 backend and the local frontend: Playwright **36 passed, 3 skipped** (the new journey runs on desktop).
- **Exit criteria (roadmap):** non-entitled module calls rejected in tests (M4) and plan changes update entitlements (M3, M5, E2E) — both pass.
- **Known gaps / residual risks:** expiry lag of up to one hour (hourly sweep); trial-at-provisioning fails soft (logged); catalogue tables writable by the runtime role (service-layer protected); module names shown as codes; snapshot without `valid_from`/`valid_until`; Phase 3 open items unchanged.
- **Next:** owner review and approval of Phase 4. Phase 5 (Customization Studio) needs a plan and approval first.

### 2026-11-22 — Session 31: Phase 4 approved; Phase 5 plan proposed
- **M7:** [PR #50](https://github.com/shafikcmt/education-erp-platform/pull/50) — CI **8/8 success**; squash-merged pinned to `fb02f59` → **`983a9e4`** (tree identical to the head).
- **Phase 4: Approved** by the owner ("approve and continue").
- **Phase 5 plan:** `docs/plans/PHASE_05_PLAN.md` (**Proposed**) with ADR-055 to ADR-059 (Proposed) and five questions (template engine, rules evaluator, self-service sign-up behind a flag, preset content review, Studio quotas). No Phase 5 code is written before approval.
- **Still open from Phase 3:** re-checking the inviter's permission at invitation acceptance.
- **Phase 5 plan: Approved** by the owner with the recommended answers (ADR-060); ADR-055 to ADR-059 Accepted. Phase 5 is **In progress**; M1 starts next.

### 2026-11-22 — Session 31 (continued): Phase 5 M1
- **Plan:** [PR #51](https://github.com/shafikcmt/education-erp-platform/pull/51) — CI **8/8 success**; merged → **`15eadb0`**.
- **M1 (`feat/phase-05-m1`):** `customization` app; declared `SETTINGS` in manifests (validated catalogue); `customization_configversion` with standard RLS and composite keys; draft / publish / rollback with diffs and audit; effective config resolver (defaults → preset hook → tenant → institution → campus) with a generation-token cache; three permissions; two real tenancy settings.
- **Verification (local):** backend **930 passed, 9 skipped** (9 new); ruff, format, mypy (252 files), import-linter 9/9, `makemigrations --check` clean; OpenAPI unchanged (no API in M1).
- **Next:** M2 (presets: repo files, owner-run sync, six v1 drafts, pinning at provisioning, terminology in `/me/context/`).

### 2026-11-22 — Session 31 (continued): Phase 5 M2
- **M1:** [PR #52](https://github.com/shafikcmt/education-erp-platform/pull/52) — CI **8/8 success**; squash-merged pinned to `b86c99e` → **`cd6f643`** (tree identical to the head).
- **M2 (`feat/phase-05-m2`):** six v1 draft presets (en + bn); preset validation; owner-only, immutable `sync_presets` (P21, disabled as a runtime scope); institutions pin their type's default preset at creation; preset layer in the resolver; capability flags, structure levels and role labels as declared keys; terminology in `/me/context/`.
- **Verification (local):** backend **942 passed, 9 skipped** (12 new, incl. the throwaway-database owner bootstrap); ruff, format, mypy (259 files), import-linter 9/9, `makemigrations --check` clean; OpenAPI (0 warnings) and client regenerated; frontend `tsc` clean.
- **Known gap:** preset content is a draft for review with real institutions (ADR-060 Q4).
- **Next:** M3 (rules sandbox with security tests; custom field definitions and JSONB validation).

### 2026-11-22 — Session 31 (continued): Phase 5 M3
- **M2:** [PR #53](https://github.com/shafikcmt/education-erp-platform/pull/53) — CI **8/8 success**; squash-merged pinned to `5e7ae70` → **`98f2ba8`** (tree identical to the head).
- **M3 (`feat/phase-05-m3`):** in-house rules sandbox with static checks and resource limits; rule namespaces in manifests; versioned rule definitions with mandatory passing test cases; custom field definitions (ten types) and value validation; four new permissions.
- **Verification (local):** backend **980 passed, 9 skipped** (38 new, incl. 34 sandbox tests); ruff, format, mypy (264 files), import-linter 9/9, `makemigrations --check` clean; OpenAPI unchanged (no API in M3).
- **Known gaps (planned for M6):** custom field values are not yet stored on tenancy entities (no `extra` columns until the APIs use them); per-plan Studio quotas (ADR-060 Q5) not yet enforced.
- **Next:** M4 (forms and DynamicForm backend; workflow engine and minimal `notifications_core`; SLA sweep).

### 2026-11-22 — Session 31 (continued): Phase 5 M4
- **M3:** [PR #54](https://github.com/shafikcmt/education-erp-platform/pull/54) — CI **8/8 success**; squash-merged pinned to `1e4d160` → **`eeef420`** (tree identical to the head).
- **M4 (`feat/phase-05-m4`):** form definitions and the DynamicForm backend (render, visibility, server-side submission validation); workflow engine (versioned specs, guards in the sandbox, permissions per transition, SLA, append-only steps, approver notifications); new `notifications_core` module (in-app + email); P24 SLA sweep; shared draft/publish helper.
- **Verification (local):** backend **986 passed, 9 skipped** (6 new M4 tests plus updated gates); ruff, format, mypy (276 files), import-linter 9/9, `makemigrations --check` clean; OpenAPI unchanged (no API in M4).
- **Next:** M5 (template sandbox with preview and security tests; numbering sequences with a concurrency test).

### 2026-11-22 — Session 31 (continued): Phase 5 M5
- **M4:** [PR #55](https://github.com/shafikcmt/education-erp-platform/pull/55) — CI **8/8 success**; squash-merged pinned to `efe969c` → **`121bbff`** (tree identical to the head).
- **M5 (`feat/phase-05-m5`):** Jinja2 template sandbox with security tests (new dependency, ADR-056); template kinds and versioned template definitions with previews; numbering sequences with gap-free, concurrency-tested allocation.
- **Verification (local):** backend **1017 passed, 9 skipped** (31 new); ruff, format, mypy (280 files), import-linter 9/9, `makemigrations --check` clean; OpenAPI unchanged (no API in M5).
- **Next:** M6 (APIs for the Studio, OpenAPI and client; custom field values on tenancy entities; Studio quotas).

### 2026-11-22 — Session 31 (continued): Phase 5 M6
- **M5:** [PR #56](https://github.com/shafikcmt/education-erp-platform/pull/56) — CI **8/8 success**; squash-merged pinned to `18b59b1` → **`4914529`** (tree identical to the head).
- **M6 (`feat/phase-05-m6`):** Studio API (configuration, fields, rules, forms, workflows, templates, numbering, catalogue), notification inbox, platform presets list; custom field values on institutions and campuses with edit checks and masking; per-plan soft Studio quotas; OpenAPI and client regenerated.
- **Verification (local):** backend **1022 passed, 9 skipped** (5 new API tests); ruff, format, mypy (288 files), import-linter 9/9, `makemigrations --check` clean; OpenAPI `--validate --fail-on-warn` clean; frontend `tsc` clean.
- **Known gap:** custom field values on members wait for member profiles (Phase 7).
- **Next:** M7 (Studio UI, DynamicForm renderer, notifications, onboarding wizard, self-service sign-up behind a flag, en + bn).

