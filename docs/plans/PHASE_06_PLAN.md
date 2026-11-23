# Phase 6 Plan — Academic Structure and Student Admission

- **Status:** **Approved** (owner, 2026-11-23: "approved all ur recommendation") with the recommended answers to Q1–Q8 (ADR-066). ADR-063 to ADR-065 Accepted.
- **Depends on:**
  - Phase 5 (**Approved** by the owner, 2026-11-23).
  - Accepted ADRs:
    - tenancy and isolation: ADR-009, ADR-043, ADR-046;
    - modules and entitlements: ADR-050 to ADR-054;
    - Customization: ADR-055 to ADR-062.
- **Roadmap scope (`DEVELOPMENT_ROADMAP.md` Phase 6):**
  - `academics`: years, terms, structure levels, the academic unit tree, subjects/courses, offerings, capability flags.
  - `timetable` (basic): periods, rooms, slots, clash detection.
  - `admissions`: inquiries, cycles, public forms, applications, the review workflow, test scheduling, the merit list, a conversion hook.
  - The full `files` module (moved here by Phase 3 plan rev. 2, Q11).
- **Roadmap exit criterion:** school, university, madrasa and coaching structures can be configured without code changes, with tests per preset.
- **Requirements:** ACA-01 to ACA-03 and ADM-01 to ADM-02 (Phase 6). Also, partly:
  - ACA-04 (timetable): see Q2.
  - ACA-05 (promotion, Phases 6–9).
  - ADM-03 (conversion, Phases 6 and 10).

## 1. Goals

1. **One academic model for six institution types.** Organisational levels come from configuration (presets and the Studio), never from `if institution_type == …`. Behaviour differences branch on capability flags, centrally:
   - `academics.credit_based`;
   - `academics.semester_based`;
   - `academics.section_enabled`.
2. **Admissions from inquiry to decision.**
   - Inquiries, then admission cycles, then a public, tenant-branded application form (a Studio form rendered by the existing DynamicForm), then review through a Studio workflow, then tests and scores, then a merit list, then an offer and its acceptance.
   - Student creation is the conversion hook (see Q3).
3. **Files.**
   - Tenant-prefixed object keys, presigned upload and download, type and size validation, quotas, a scan-state machine and retention.
   - Built on the Phase 3 `tenant_storage_key()` helper and the existing `django-storages`/`boto3` dependencies. No new dependency.
4. **The same guarantees as every phase:**
   - RLS on every tenant table;
   - permissions checked in views and services;
   - module entitlement on every route;
   - isolation tests, en and bn, mobile-first;
   - tenant hosts stay disabled.

## 2. Academic structure (proposed ADR-063)

- **Time dimension (dedicated models):**
  - `academics_academicyear`: institution, code, name, start and end dates, status `planned | active | closed`. At most one active year per institution. Dates must not overlap within an institution.
  - `academics_term`: year, kind `term | semester | trimester | quarter` (from configuration), order, dates inside the year. Terms are required only when `academics.semester_based` is true.
- **Organisational tree (generic):**
  - `academics_unit`: institution, campus (optional), parent (composite tenant key), `level_key`, code, name and `name_i18n`, capacity, order, `archived_at`.
  - The level keys are the institution's effective `customization.structure_levels`, broadest first. A unit's level must be exactly one below its parent's level.
  - This stores, through configuration alone:
    - Class → Section (school);
    - Faculty → Department → Program (university);
    - Marhala → Jamaat (madrasa);
    - Program → Batch (coaching).
  - When `academics.section_enabled` is false, the lowest grouping level is the class itself.
- **Subjects and courses:**
  - `academics_subject`: institution, code, name and `name_i18n`, `subject_type` (configurable list, for example core and elective), `credits NUMERIC(5,2)` (required when `academics.credit_based` is true, otherwise null), `archived_at`.
- **Offerings:**
  - `academics_offering`: year, optional term, unit, subject, optional credits override.
  - `academics_offeringteacher`: offering, membership, role `primary | assistant`.
  - Teachers are tenant memberships now; Phase 7 links staff profiles to the same membership (see Q7).
- **Structure levels become configuration-only for organisational levels.**
  - The v1 presets also list time and subject levels (`academic_year`, `semester`, `subject`, `course`). Phase 6 adds **v2 presets** whose `customization.structure_levels` contain organisational levels only, with en and bn labels.
  - Presets are immutable and new versions are opt-in (ADR-058). New institutions pin v2. Existing institutions stay on v1 until an administrator moves them; academics ignores the non-organisational keys of a v1 preset.
- **Integrity:**
  - The Studio refuses to publish a configuration that removes or reorders a level that units already use. This is a validation hook declared by `academics`, so `customization` never imports `academics`.
  - Archiving a unit with live children or offerings is refused.
- **Promotion (ACA-05):** promotion needs students, so it moves to Phase 7. Phase 6 adds only the promotion rule namespace for the sandbox (`academics.promotion`), so rules can be drafted and tested.

## 3. Timetable (see Q2)

- The module catalogue declares `timetable` as depending on `academics` **and `staff`**, and `staff` is Phase 7. Teacher clash detection needs the teachers' profiles and availability.
- **Recommendation:** move `timetable` to Phase 7, right after `staff`, and keep the catalogue dependency.
- **Alternative:** build periods, rooms and slots now, with teacher clashes keyed by membership. That means changing the catalogue dependency and revisiting it in Phase 7.

## 4. Admissions

- **Inquiries:** `admissions_inquiry`. Fields:
  - institution;
  - contact (name, phone and/or email);
  - interest (unit or level, free text);
  - source (configurable list);
  - status `new | contacted | converted | closed`;
  - assigned member;
  - follow-up date;
  - notes.

  Staff create inquiries. A public inquiry form is optional, using the same abuse controls as applications.
- **Cycles:** `admissions_cycle`. Fields:
  - institution and academic year;
  - target units (the levels admitted to);
  - opening and closing dates;
  - a published Studio **form** (entity `admissions.application`, declared in `CUSTOM_FIELD_ENTITIES` with core fields);
  - an optional Studio **workflow** (subject `admissions.application`, declared in `WORKFLOW_SUBJECTS`);
  - an optional **merit rule** (namespace `admissions.merit`);
  - capacity per target unit;
  - an application number sequence (Studio numbering);
  - status `draft | open | closed | archived`.
- **Applications:** `admissions_application`. Fields:
  - cycle and target unit;
  - number (allocated without gaps from the cycle's sequence);
  - applicant core fields;
  - `extra` JSONB (validated custom values);
  - `email_verified_at`;
  - status `draft | submitted | under_review | test_scheduled | evaluated | offered | accepted | declined | rejected | withdrawn`;
  - workflow instance;
  - score and merit rank;
  - decision fields.

  Staff may also enter applications on an applicant's behalf, through the same validation path.
- **Public application flow (tenant host, anonymous; proposed ADR-065):**
  1. `GET /api/v1/public/admissions/cycles/` lists open cycles. `GET …/{id}/form/` returns the published form, rendered by the existing DynamicForm. Visibility rules run on the server.
  2. `POST …/{id}/applications/` validates the submission on the server and sends a single-use email verification link. Only its hash is stored, and the response is the same for every input.
  3. Verification turns the draft into `submitted`, allocates the number and emails a **status link**: a hashed, long-lived token that is revocable and rotated on demand. There are no applicant accounts (see Q6).
  4. With the status link, the applicant sees their status, test schedule and decision, and can accept or decline an offer.
- **Abuse controls (as in Phase 5 sign-up):**
  - a per-IP limit (429) and a silent per-email limit per cycle;
  - a honeypot field;
  - drafts expire after 48 hours and are purged;
  - every answer is the same whether or not an email address is known.
  - Applicant PII is visible only to holders of `admissions.application.view` in the institution's scope.
- **Review:**
  - The cycle's workflow drives the states, with the permission per transition, guards, SLA and notifications from Phase 5.
  - Without a workflow, a built-in minimal path applies: submitted → under review → offered or rejected.
- **Tests and merit:**
  - `admissions_test`: cycle, name, date and time, venue (free text), capacity, maximum score.
  - `admissions_testassignment`: application, test, seat, score, `absent`.
  - The merit list ranks evaluated applications by the cycle's merit rule (sandbox, `Decimal`, tie-breaks declared in the rule) or by total score.
  - Publishing it freezes the ranking as a version. Offers follow the ranks up to capacity, and a declined offer moves the next applicant up.
- **Conversion (see Q3):**
  - An accepted application raises the domain event `admissions.application.accepted` and stays `accepted`.
  - Phase 7 consumes the event to create the student, guardians and enrollment.
  - The fee assignment waits for Phase 10.
- **Application fee (see Q5):** a cycle may show a fee amount (`NUMERIC(18,2)` plus a currency). Collection waits for the `fees` module and payment gateways (ADR-017, Phase 10).

## 5. Files (proposed ADR-064)

- `files_file` (tenant RLS). Fields:
  - key (`tenant_storage_key()`, never chosen by clients);
  - owner object (type and id);
  - purpose (declared by modules, for example `admissions.document`);
  - original name;
  - declared and detected MIME type;
  - size;
  - SHA-256;
  - scan state `pending | clean | infected | unscanned`;
  - retention class;
  - uploader (membership or "applicant");
  - `deleted_at`.
- **Uploads:**
  1. The client asks for an upload slot: purpose, name, size and type are validated against the purpose's allow-list and limits.
  2. The server answers with a presigned POST that has a size limit, a content type and a short expiry.
  3. The client confirms the upload. The server checks the object's size, type and hash, then the file is usable.
- **Downloads:**
  - Presigned GET links that expire within minutes, issued only after the permission check for the owner object.
  - The content disposition is `attachment`, so uploaded files are never served inline as HTML.
- **Malware scanning (see Q8):**
  - A scanner interface with a pluggable backend. The default backend `none` marks files `unscanned`.
  - Unscanned files are downloadable only by staff, with a warning, and never by applicants.
  - Choosing a real scanner (for example a ClamAV container) is an infrastructure decision for Phase 18.
- **Quotas and retention:**
  - per-tenant storage usage is metered against the plan limit `max_storage_mb` (billing accepts the key);
  - per-purpose limits on count and size;
  - orphaned uploads (never confirmed) are deleted after 24 hours;
  - purpose retention classes drive deletion.
- **Public uploads:** applicants upload against their verified draft application only, at most 5 files of 5 MB each, PDF, JPEG or PNG only.

## 6. Platform operations (catalogue additions)

| # | Operation | Actor | Mechanism |
|---|---|---|---|
| P26 | Admissions housekeeping: expire and purge unverified drafts, close cycles past their dates | system | I |
| P27 | Files housekeeping: delete unconfirmed uploads, apply retention | system | I |

Public application endpoints are **tenant-host** routes. The host resolves the tenant (P1) and runs one tenant transaction per request, so they need no platform scope. They are added to the reviewed anonymous allow-list.

## 7. Permissions (new codes)

- `academics.year.view|manage`
- `academics.structure.view|manage` (units)
- `academics.subject.view|manage`
- `academics.offering.view|manage`
- `admissions.inquiry.view|manage`
- `admissions.cycle.view|manage`
- `admissions.application.view|review|decide`
- `admissions.test.manage`
- `admissions.merit.publish` (MFA and step-up)
- `files.file.view|upload` (most file access goes through the owner object's permission)

Role templates (system copies are synced by P7):

| Role | New permissions |
|---|---|
| `institution_admin` | all of the above in its institution |
| `academic_coordinator` | academics manage; admissions view |
| `admission_officer` | inquiries, cycles view, applications view and review, tests |
| `exam_controller` | test scores |
| `front_desk` | inquiries |
| `teacher` | academics view (structure, own offerings) |

## 8. API and frontend

- **Tenant-host APIs** under `/api/v1/academics/…`, `/api/v1/admissions/…` and `/api/v1/files/…`:
  - every view declares its module;
  - services re-check the exact scope without the cache;
  - lists are paginated;
  - OpenAPI is generated with `--fail-on-warn`, plus the TypeScript client.
- **Public tenant-host APIs** under `/api/v1/public/admissions/…`: anonymous, throttled, enumeration-safe, and listed on the reviewed allow-list.
- **Screens (en and bn, mobile-first):**
  - academic setup: years and terms, a structure tree editor with the effective level labels, subjects, offerings with teachers;
  - admissions: cycles (form, workflow, merit rule, capacity), inquiries, applications (list, detail, documents, workflow actions), tests and scores, merit list and offers;
  - public pages on the tenant host: the cycle list, the application form (DynamicForm), the verification page, the status page.
  - The navigation follows permissions and entitlements, as before.

## 9. Milestones

| # | Scope |
|---|---|
| M1 | `academics` data model: years, terms, units, subjects, offerings; RLS, composite keys and services; capability-flag branching in one place; v2 presets; level-integrity hook. Tests per preset |
| M2 | `academics` API, OpenAPI and client; role template updates |
| M3 | `files`: model, presigned upload and download, purposes, limits, scan states, quotas, P27 |
| M4 | `admissions`: inquiries, cycles (form, workflow, merit rule, numbering bindings), staff-entered applications, the review workflow |
| M5 | Public application flow: open cycles, form, submission, email verification, status link, uploads, abuse controls, P26 |
| M6 | Tests, scores, merit list (sandbox namespace), offers, acceptance and decline, the `admissions.application.accepted` event |
| M7 | Frontend: academic setup, admissions back office, public pages; en and bn |
| M8 | E2E (school, university, madrasa and coaching structures configured without code; the public application journey to an accepted offer); docs; security self-review; Phase 6 PR |

## 10. Proposed ADRs

- **ADR-063:** academic structure.
  - Dedicated year and term models.
  - One generic unit tree whose levels come from the effective `customization.structure_levels`, with v2 presets containing organisational levels only.
  - Capability flags branch centrally.
  - Offering teachers are memberships.
- **ADR-064:** the `files` module.
  - Server-chosen tenant keys, presigned POST and GET, purposes with limits.
  - The scan-state machine with a pluggable scanner (default `none`, meaning unscanned and staff-only).
  - Quotas through the plan key `max_storage_mb`.
  - No new dependency.
- **ADR-065:** public admissions on tenant hosts.
  - Anonymous, throttled, enumeration-safe.
  - Email-verified drafts and hashed status links instead of applicant accounts.
  - Uploads only against verified drafts.
- **ADR-066:** the owner's answers to §11 (all eight recommendations).

## 11. Questions for the owner

1. **Structure model:** configuration-driven levels plus one generic unit tree, with v2 presets that keep only organisational levels? The alternative is separate tables per institution type, which contradicts CLAUDE.md §4. **Recommendation:** the generic tree, ADR-063.
2. **Timetable:** move it to Phase 7 right after `staff`, because it depends on staff in the catalogue and needs teacher profiles; or build it now keyed by memberships? **Recommendation:** move it to Phase 7.
3. **Student creation:** stop Phase 6 at an accepted application plus the conversion event, and create students in Phase 7 with the full student model; or introduce a minimal student table now? **Recommendation:** stop at the event, so no throw-away schema.
4. **Files and public uploads:** build `files` in Phase 6 and let applicants attach documents (PDF, JPEG or PNG, at most 5 files of 5 MB each, against verified drafts only)? **Recommendation:** yes.
5. **Application fee:** show the amount only, and collect it with `fees` and payment gateways in Phase 10? **Recommendation:** yes. Actual prices and gateways are not decided.
6. **Applicant identity:** no applicant accounts, but email-verified drafts and a hashed, revocable status link; or applicant accounts in `identity`? **Recommendation:** status links. Accounts arrive with the student and guardian portal in Phase 7.
7. **Teacher assignment:** reference tenant memberships now, and link staff profiles to the same membership in Phase 7? **Recommendation:** yes.
8. **Malware scanning:** ship the scanner interface with the default `none` (files `unscanned`, staff-only, never shown to applicants) and choose a real scanner in Phase 18? **Recommendation:** yes. A scanner container is a new infrastructure dependency and needs its own decision.

## 12. Exit criteria

- School, university, madrasa and coaching structures are configured through presets and the Studio, with no code changes. There are tests per preset and a cross-preset test that runs the same code paths.
- Capability flags change behaviour, for example credits required when credit-based and terms required when semester-based. There is a test per flag.
- The public application journey runs end to end through the real stack: form, verification, status link, review workflow, test score, merit list, offer, acceptance.
- Every new tenant table has RLS and isolation tests. The URL audit, catalogue completeness, host-route review and anonymous allow-list pass. The abuse controls are tested.
- Tests, lint, type checks, OpenAPI drift, E2E and CI all pass. The docs, progress file, decision log and security self-review are updated.

### Change notes
- 2026-11-23 — Created (Proposed).
- 2026-11-23 — Approved by the owner with all recommended answers (ADR-066); ADR-063 to ADR-065 Accepted. `timetable` moves to Phase 7 (Q2).
