# Phase 6 — Security Self-Review (M8)

- **Scope:** everything Phase 6 added (M1–M8; plan `docs/plans/PHASE_06_PLAN.md`; ADR-063–066):
  - the `academics` structure (years, terms, units, subjects, offerings) and capability flags;
  - the `files` module (presigned uploads and downloads, scanning hook, quotas, housekeeping P27);
  - the `admissions` back office (inquiries, cycles, applications, review, decisions);
  - the public application flow on tenant hosts (P26);
  - admission tests, scores, merit lists and offers;
  - the Phase 6 frontend and the browser-upload CSP change.
- **Method:**
  - I read every new code path.
  - The automated gates ran: isolation registry, RLS coverage, URL authorization audit, catalogue completeness, host-route review, anonymous allow-list and the migration rehearsal.
  - Targeted tests ran: abuse controls, cross-tenant tokens, scope 404s, the step-up on merit publication and the fail-closed merit rule.
  - The real-stack E2E (`frontend/e2e/admissions.spec.ts`) runs the public journey with a real presigned upload to the object store.
- **Status:** this is a self-review by the implementer. It is not an independent review and does not replace the owner's approval.
- **Tenant hosts:**
  - Tenant hosts stay disabled in every committed configuration.
  - Tenant hosts, sign-up and the browser-upload origin are enabled only in the throwaway CI/local E2E stack.

## 1. Defects found and fixed during Phase 6

| # | Defect | How it was found | Fix |
|---|---|---|---|
| F1 | A configuration read inside a publishing transaction cached the not-yet-committed values, which then survived a rollback | M1 tests | The resolver stores nothing while a publish of the connection is uncommitted |
| F2 | Storage I/O was attempted inside a nested tenant transaction in tasks | M3 tests | Task bodies already run in the tenant transaction; network I/O (`head`, `delete`) is refused inside an open tenant transaction |
| F3 | Public routes would have passed the module gate for anonymous callers | M5 review | Public views check the entitlement themselves and answer 404 without the module |
| F4 | Exam controllers held `admissions.test.manage` but could not find any test (no cycle view) | M7 review | `GET /admissions/tests/?institution=` gated by `admissions.test.manage`; still 404 outside the caller's institutions |
| F5 | The CSP blocked the browser's presigned upload to the object store | M7 review | One validated bare origin (`FILES_UPLOAD_ORIGIN`) joins `connect-src`; empty by default |
| F6 | Opening the emailed status link again in the same tab showed stale data (hash-only navigation) | M8 E2E | `useFragmentToken` also reads new fragments on `hashchange`; unit-tested |

## 2. Review of the attack surface

| Area | Finding |
|---|---|
| **Tenant isolation** | <ul><li>Every new tenant table has standard RLS (ENABLE + FORCE): 6 academics tables, `files_storedfile`, and 7 admissions tables.</li><li>Composite tenant/institution/cycle keys keep children inside one institution. For example, a test assignment's test and application share a cycle, and a merit list's target belongs to its cycle.</li><li>Isolation migrations refuse reversal, and every module has cross-tenant tests.</li><li>No runtime `BYPASSRLS` was introduced, and no runtime service holds owner credentials.</li></ul> |
| **Authorization** | <ul><li>Every view declares its module and its permission. Services re-check the exact institution scope without the cache.</li><li>An institution, cycle, test or target outside the caller's institutions answers 404.</li><li>`admissions.merit.publish` needs MFA and a fresh step-up, which the API test covers.</li><li>Applicant personal data needs `admissions.application.view`. The exam controller gets only `admissions.test.manage`: seat lists (number and name), no application files.</li><li>Names are not frozen into published merit lists.</li></ul> |
| **Public flow (ADR-065)** | <ul><li>Every public route is on the reviewed anonymous allow-list, on tenant hosts only, and answers 404 without the module.</li><li>Submitting always returns the same 202 response.</li><li>A per-IP limit answers 429. The per-email limit per cycle and the honeypot are silent.</li><li>Only SHA-256 hashes of single-use, expiring tokens are stored. The tokens travel in the URL fragment and the request body, never the path, and live only in page memory.</li><li>Verification needs a click, so mail scanners can't submit.</li><li>The audit metadata never contains the email.</li><li>Unverified drafts are purged after 48 hours (P26).</li><li>A status token does not work on another tenant's host, which is tested.</li></ul> |
| **Files (ADR-064)** | <ul><li>Keys are chosen by the server under the tenant prefix.</li><li>Purposes allow-list the types (no browser-active content) and limit size and count.</li><li>Presigned POSTs bind the key, the content type and the size range, and expire after 10 minutes.</li><li>The stored object is checked by a worker before the file is usable.</li><li>Downloads are short-lived (5 minutes) and use `attachment` disposition. Infected files are never served. Unscanned files reach staff only, with a warning.</li><li>Unconfirmed uploads are deleted (P27).</li></ul> |
| **Browser uploads** | <ul><li>The upload is a multipart POST, a CORS "simple" request, sent with `no-cors`. The object store needs no CORS rule, and the response is opaque by design.</li><li>The server's verification decides whether the file exists and fits; a failed upload shows as a rejected document.</li><li>The CSP adds only the configured bare origin.</li></ul> |
| **Merit rules (ADR-055)** | <ul><li>Rules run in the Phase 5 sandbox with `Decimal` arithmetic and declared variables only: the application's core and custom values, the total score and `today`.</li><li>A rule that can't be evaluated for any application stops the publication (fail closed).</li><li>Only applications whose review workflow is finished are ranked.</li></ul> |
| **Offers** | <ul><li>Seats are counted under a row lock on the target.</li><li>A decline frees the seat, and the next waiting applicant of the latest published list is offered it automatically. This is audited as a system action (`via=decline`).</li><li>Acceptance calls the Phase 7 hook after commit.</li></ul> |

## 3. Residual risks and open items (for the owner)

1. **No malware scanner yet** (ADR-066 Q8). Files stay `unscanned` and reach staff only. Choosing a scanner is a Phase 18 infrastructure decision.
2. ~~**Automatic offer on decline.**~~ Decided by ADR-067 (2026-11-24): kept as is.
   - The plan says a decline moves the next applicant up, so it is automatic and audited.
   - If you prefer a manual step, staff would press "Offer free seats" instead. This is a small change.
3. ~~**The exam controller role holds `admissions.test.manage`.**~~ Resolved by ADR-067 (2026-11-24): the exam controller now holds only `admissions.test.score`. It can schedule tests as well as score them. A separate score-only code is possible if you want it.
4. **Applicants are not emailed about decisions or offers.** They see them through the status link. Notifications are extended in Phase 14.
5. **One client address in E2E.** The local and CI stack reaches the API from one Docker gateway address, so per-IP limits are shared there. Production sees real client addresses through Nginx.
6. **Preset content is a draft** (ADR-060 Q4). It must be validated with real institutions.
7. **UI gaps:**
   - no staff application-entry screen;
   - no screens for terms and offerings;
   - Studio keys are typed in the cycle dialog.

   The API covers all three, and the server validates everything.
8. **Still open from earlier phases:** the items moved to Phase 18 (D9 benchmark, prefork K6, alerting).

### Change notes
- 2026-11-24 — Created (Phase 6 M8).
- 2026-11-24 — Owner approved Phase 6; items 2 and 3 decided by ADR-067.
