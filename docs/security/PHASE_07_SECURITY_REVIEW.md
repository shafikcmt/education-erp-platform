# Phase 7 — Security Self-Review (M10)

- **Scope:** everything Phase 7 added (M1–M10; plan `docs/plans/PHASE_07_PLAN.md`; ADR-068–074):
  - `students`: students, guardians, enrollments, relationship scopes, lifecycle, transfer certificates, documents from Studio templates, bulk import (P28), conversion from admissions, portal invitations;
  - `staff`: profiles, departments, designations, class-teacher advisors;
  - `timetable`: bell schedules, periods, rooms, slots and clash detection;
  - `parent_portal`: the guardian and student portal;
  - small changes elsewhere: the tenancy invitation-acceptance hook, `files` (bounded read, XLSX type), the admissions staff-entry endpoints, `core.people`, and the backend image's linux-pam upgrade;
  - the Phase 7 frontend.
- **Method:**
  - I read every new code path.
  - The automated gates ran: isolation registry and RLS coverage on the 13 new tables, URL authorization audit and host-route review for every new route, catalogue completeness (108 codes), import contracts, migration check, OpenAPI drift, Trivy on both images.
  - Targeted tests ran: object-level visibility per relationship (allowed and denied), 404 for hidden objects, step-up on promotion and import, clash detection directly against the database, cross-tenant isolation per module.
  - The real-stack E2E (`frontend/e2e/people.spec.ts`) runs the students → guardian → staff → timetable → import → guardian-portal journey with a real upload to the object store, the worker and real email.
- **Status:** this is a self-review by the implementer. It is not an independent review and does not replace the owner's approval.
- **Tenant hosts:** they stay disabled in every committed configuration; they are enabled only in the throwaway CI/local E2E stack.

## 1. Defects found and fixed during Phase 7

| # | Defect | How it was found | Fix |
|---|---|---|---|
| F1 | A campus-scoped teacher saw no students: relationship checks looked only at the institution scope | M2 object-level tests | `holds_in_institution` accepts the code held for the institution or one of its campuses |
| F2 | A too-short guardian search returned a server error | M2 tests | A 400 validation error |
| F3 | Without a home campus, a campus admin's `staff.profile.view` would have shown the whole institution's staff | M3 design review | An optional home campus on profiles; campus scope covers only that campus's staff |
| F4 | Audit metadata keyed `code` was refused as sensitive | M3 tests | The reference key is `ref` |
| F5 | Invited guardians and students hold their role in an institution, so tenant-only checks of `students.child.view` / `profile.view_own` would have shown them nothing | M8 design | The relationship codes count in any scope (`holds_anywhere`); they still open only one's children or oneself |
| F6 | The backend image failed Trivy: CVE-2025-6020 (HIGH, linux-pam), fixed by Debian after the base image was pinned | M8 CI | Upgrade only the PAM packages in the runtime stage, failing closed (`apt-get update --error-on=any` and a version check); a plain `apt-get update` only warns, which would have hidden a no-op upgrade |
| F7 | Bell schedule periods were untyped in OpenAPI | M9 type check | Schema annotation; the client is typed end to end |
| F8 | Staff application entry needed the Studio form, which admission officers can't read through Studio | M9 review | Two staff endpoints render the cycle's form behind `admissions.application.review` in the cycle's institution (tested allowed and denied) |

## 2. Review of the attack surface

| Area | Finding |
|---|---|
| **Tenant isolation** | <ul><li>Every new tenant table has standard RLS (ENABLE + FORCE): 7 students tables, 4 staff tables, 4 timetable tables (and none in `parent_portal`).</li><li>Composite tenant/institution keys keep children inside one institution: an enrollment's student, year and unit; a profile's campus, department and designation; an advisor's year, unit and profile; a slot's year, term, unit, period and room; a transfer certificate's student. The database refusals are tested.</li><li>Isolation migrations refuse reversal; every module has cross-tenant tests.</li><li>No runtime `BYPASSRLS`; no runtime service holds owner credentials.</li></ul> |
| **Relationship scopes (ADR-073)** | <ul><li>One selector per relationship, used by every list and detail: staff scope (tenant, institution, campus through enrollment), assigned (taught offerings and class-teacher advisors, through the `STUDENTS_ASSIGNED_UNITS` hook), child, own.</li><li>Hidden and unknown students both answer 404.</li><li>Guardians see only their own guardian link, never another guardian's contact details.</li><li>The portal uses only the child and own grounds, never staff scope.</li><li>Timetables: staff need the timetable and structure view codes; guardians and students see only their children's or their own units.</li></ul> |
| **Authorization** | <ul><li>Every view declares its module and permission; services re-check the exact institution scope without the cache.</li><li>Promotion and student import need MFA and a fresh step-up (tested at the API).</li><li>Role templates: nobody grants a code they don't hold; the owner and institution admin now hold the child/own/portal codes so they can invite guardians and students, and those codes open nothing else for them.</li><li>Assigning class teachers uses `academics.offering.manage`, the same authority as subject teachers.</li></ul> |
| **Portal invitations (ADR-069)** | <ul><li>The reviewed Phase 3 flow, unchanged: hashed single-use tokens, email match, inviter re-check (ADR-062), no escalation.</li><li>The linking hook runs in the acceptance transaction, only for invitations recorded as portal invitations, and never overwrites an existing login.</li><li>Phone-only guardians get no login until phone sign-in (ADR-074 Q2).</li></ul> |
| **Conversion from admissions** | <ul><li>Runs as a tenant task after commit; idempotent (one student per application, database constraint); module-gated.</li><li>Reads admissions through a selector, not its tables.</li><li>Failures (e.g. the plan's student limit) are audited with the reason only; staff can retry with `students.student.manage`.</li></ul> |
| **Bulk import (ADR-072)** | <ul><li>The file is the uploader's own verified `files` object, read only in the task body (no storage I/O in a request transaction).</li><li>CSV must be UTF-8; XLSX is read with `openpyxl` read-only, first sheet, refused above 40 MB uncompressed or 100× its size (zip bombs); Python's expat limits entity expansion.</li><li>5 000 rows and 60 columns at most; each row runs through the normal services in its own savepoint, so permissions, validation and plan limits apply per row; the dry run writes nothing (tested).</li><li>The downloadable report neutralises formula-looking cells.</li><li>Jobs (their reports hold personal data) and files are deleted after 30 days (P28).</li></ul> |
| **Printable documents** | <ul><li>ID cards and transfer certificates render from published Studio templates of their exact kind in the sandboxed engine (ADR-056) with autoescape (tested with a name containing HTML).</li><li>The browser shows them only in an iframe with `sandbox=""` and `srcdoc`: no scripts, no forms, no same-origin access.</li></ul> |
| **Timetable** | <ul><li>Unique constraints make double booking impossible for the same unit, teacher or room and period, even for concurrent writers (tested against the database).</li><li>The service also refuses overlapping periods of other bell schedules and whole-year against term lessons.</li></ul> |
| **Supply chain** | <ul><li>One new dependency, `openpyxl` 3.1.5 (MIT), approved in ADR-074 Q3, pinned in `uv.lock`; the dependency audit passes.</li><li>The backend image upgrades linux-pam for CVE-2025-6020; Trivy passes on both images.</li></ul> |

## 3. Residual risks and open items (for the owner)

1. **Guardian-visible student documents** are not built: student documents have a file purpose but no upload API or visibility flag yet.
2. **Staff imports need the `students` module** entitled, because the import endpoints belong to it.
3. **The document preview inherits the page's CSP**, so inline styles inside a Studio template may not apply in the preview; server PDF arrives in Phase 9 (ADR-074 Q5).
4. **Cross-schedule clashes** are refused by the service, not by a constraint: two concurrent writers on overlapping periods of different bell schedules could both succeed. Same-period clashes are constraint-backed.
5. **Phone sign-in for guardians** waits for an SMS provider (ADR-074 Q2, Phase 14; the provider is the owner's decision).
6. **Still open from earlier phases:** no malware scanner (ADR-066 Q8); applicant decision emails (Phase 14); preset content is a draft (ADR-060 Q4); the items moved to Phase 18 (D9 benchmark, prefork K6, alerting); one client address in the E2E stack.
