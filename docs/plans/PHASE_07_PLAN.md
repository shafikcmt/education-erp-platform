# Phase 7 Plan — Student, Teacher and Parent Management

- **Status:** **Approved** (owner, 2026-11-26: "approval all ur recommended and continue develop same") with the recommended answers to Q1–Q8 (ADR-074). ADR-068 to ADR-073 Accepted.
- **Depends on:**
  - Phase 6 (**Approved** by the owner, 2026-11-24; ADR-063 to ADR-067).
  - Accepted ADRs:
    - tenancy and isolation: ADR-009, ADR-043, ADR-046;
    - modules and entitlements: ADR-050 to ADR-054;
    - Customization: ADR-055 to ADR-062;
    - academics, files and admissions: ADR-063 to ADR-067.
- **Roadmap scope (`DEVELOPMENT_ROADMAP.md` Phase 7):**
  - `students`: profiles, guardians (N–N), enrollments, documents, bulk import, promotion and transfer, transfer certificate, ID cards via templates;
  - `staff`: profiles, departments, designations, teaching assignments;
  - `parent_portal`: guardian and student portal shells, child switcher;
  - `timetable` (basic: periods, rooms, slots, teacher and room clash detection; moved here by ADR-066 Q2);
  - admission → enrollment conversion completed;
  - scoped selectors (teacher → own sections, guardian → own children).
- **Roadmap exit criteria:** object-level scope tests pass; the import validates and reports errors.
- **Requirements:** PPL-01 to PPL-07 and ACA-04 (Phase 7). Also, partly:
  - ACA-05 (promotion, Phases 6–9): bulk promotion now; result-based rules in Phase 9.
  - ADM-03 (conversion, Phases 6 and 10): student and enrollment now; the fee assignment in Phase 10.

## 1. Goals

1. **One student record for every institution type.**
   - A student belongs to an institution and is enrolled, per academic year, in a unit of the Phase 6 tree (a section, a jamaat, a batch, a program).
   - There is no per-type code. Studio custom fields extend students, guardians and staff.
2. **People, not just accounts.**
   - Students, guardians and staff exist as records whether or not they have a login.
   - A login is linked when the person is invited.
   - One person keeps one account across roles: for example, a teacher who is also a guardian (CLAUDE.md §9).
3. **Scope by relationship (new).**
   - Today authorization knows tenant, institution and campus scopes.
   - Phase 7 adds **relationship scopes**, checked in selectors and services:
     - a teacher sees the students of the units and offerings they teach;
     - a guardian sees only their own children;
     - a student sees only themselves.
4. **Admission completes.** An accepted application becomes a student with guardians and an enrollment, without retyping.
5. **The same guarantees as every phase:**
   - RLS on every tenant table;
   - permissions in views and services;
   - module entitlement on every route;
   - isolation tests, en and bn, mobile-first;
   - tenant hosts stay disabled.

## 2. Students (proposed ADR-068)

- **Tables** (all tenant-owned, standard RLS, composite tenant/institution keys):
  - `students_student`:
    - institution, student number (a gap-free Studio numbering sequence, unique per institution);
    - names (with `name_i18n`), date of birth, gender (configurable list), photo (a `files` id);
    - status `active | inactive | transferred | alumni | withdrawn`;
    - optional linked membership (portal login);
    - `extra` JSONB validated by Studio custom fields (entity `students.student`);
    - the source application, if any.
  - `students_guardian`: name, phone, email, relation defaults, optional linked membership, `extra` (entity `students.guardian`).
  - `students_studentguardian`: student, guardian, relation, `is_primary`, `can_pickup`, `receives_notices`. A guardian has many children and a child has many guardians (N–N).
  - `students_enrollment`:
    - student, academic year, unit (the leaf the student sits in), roll number, status `active | promoted | repeated | transferred | completed`, start and end dates;
    - at most one active enrollment per student and year (a partial unique constraint).
  - Documents are `files` rows with the purpose `students.document` and owner `students.student`. This reuses ADR-064; there is no new table.
- **Lifecycle services:**
  - create and update student;
  - add and link a guardian;
  - enroll;
  - transfer between units (within the year);
  - withdraw;
  - **bulk promotion** at year end: from a source unit to a target unit in the next year, per student promote, repeat or complete, previewed then applied in one transaction;
  - **transfer certificate:**
    - status `transferred`, a TC number from a Studio sequence, a reason;
    - a printable document from a Studio template (sandboxed, ADR-056).
  - **alumni:** completion of the final level marks the student alumni.
- **Promotion rules:** the namespace `academics.promotion` (declared in Phase 6) may suggest promote or repeat from the variables available now: the student's fields and custom values. Results and attendance variables arrive in Phases 8–9. The staff member always confirms.

## 3. Guardians and the portal (proposed ADR-069)

- **Portal access by invitation:**
  - A guardian or student with an email address can be invited to the organisation (the Phase 3 invitation flow, roles `guardian` or `student`).
  - Accepting links their membership to the guardian or student record.
  - One account serves several children, and a guardian who is also staff keeps one account.
- **Phone-only guardians** are common in Bangladesh. They keep a record without a login until phone sign-in exists (OTP by SMS, Phase 14; see Q2).
- **`parent_portal` in Phase 7 (shells):**
  - a home screen with a child switcher;
  - each child's profile and enrollment (read-only);
  - their timetable;
  - documents marked visible to guardians.

  Attendance, results, fees and notices plug in during Phases 8–14.
- The **student portal** shows the same views for the student themselves.

## 4. Staff (proposed ADR-070)

- **Tables:**
  - `staff_department`: per institution, optional parent; covers academic and administrative departments.
  - `staff_designation`: per institution, for example Lecturer, Ustad, Accountant.
  - `staff_profile`:
    - institution, staff number (Studio sequence), names, contact, joining date, status, department, designation, employment type;
    - an optional membership (a login);
    - `extra` validated by custom fields (entity `staff.profile`);
    - HR-sensitive custom fields masked by their view permission (Phase 5 field masking).
- **Teaching assignments:** Phase 6 offering teachers reference memberships (ADR-063). A teacher's staff profile links the same membership, so assignments need no migration. A class teacher (advisor) is assigned per enrollment unit and year: `staff_unitadvisor`.
- **Staff without a login** (for example support staff) are allowed. Teaching requires a membership.

## 5. Timetable (proposed ADR-071)

- **Tables:**
  - `timetable_bellschedule` and `timetable_period`: per institution; named periods with start and end times, and breaks;
  - `timetable_room`: per campus, with capacity;
  - `timetable_slot`: academic year (and term, where semester-based), unit, weekday, period, offering, teacher (from the offering), room.
- **Clash detection**, on the server, in the same transaction:
  - one teacher, one room and one unit per weekday and period;
  - the check is backed by unique constraints, so concurrent writers cannot double-book.
- **Views:** a unit's timetable, a teacher's own timetable and a room's timetable. Guardians and students see their unit's timetable in the portal.
- **Not in Phase 7:** substitutions and automatic timetable generation.

## 6. Admission → enrollment (completes ADR-065's conversion)

- On acceptance, the `ADMISSIONS_ACCEPTED_HANDLERS` hook (Phase 6) creates, after commit, in its own tenant task:
  - the **student**, from the application's promoted and core values, with matching custom values copied when the field keys match;
  - the **guardian(s)**, matched by email or phone within the tenant to avoid duplicates (staff can merge);
  - the link from the application to the student.
- The **enrollment** is created when staff choose the leaf unit, for example the section inside the admitted class (see Q4). If the admitted target is already a leaf unit, the enrollment is created at once.
- The hook is idempotent (one student per application).

## 7. Bulk import (PPL-05, proposed ADR-072)

- **Formats:** CSV (standard library) and **XLSX** (needs `openpyxl`, a new dependency; see Q3).
- **Imports:** students with guardians and enrollment, and staff.
- **Flow:**
  1. Upload the file (`files`, purpose `students.import`).
  2. Map the columns: core fields, custom fields, guardian columns.
  3. **Dry run:** validate every row with the same services and validators. The result is a per-row error report (downloadable CSV).
  4. **Apply** in batches. Each row is atomic, and the report shows what was created.
- **Limits and safety:**
  - limits: 5 000 rows per file, and a new plan limit key `max_active_students` enforced on the server for every way a student is created. The key's default lives in the existing quota defaults; actual plan values are data and are not decided (CLAUDE.md §8);
  - runs as a tenant task;
  - formula-injection-safe exports (no cell starts with `=`, `+`, `-`, `@`);
  - the original file is deleted after a retention period.

## 8. Relationship scopes (proposed ADR-073)

- **New permission codes check relationships, not just organisational scope:**
  - `students.student.view` (institution or campus scope): staff with that scope.
  - `students.student.view_assigned`: teachers. Only students enrolled in units where the teacher is the advisor or teaches an offering in that year.
  - `students.child.view`: guardians. Only students linked to their guardian record.
  - `students.profile.view_own`: students. Only themselves.
  - `staff.profile.view_own`: staff, their own profile.
- **Enforcement:**
  - One selector per relationship, used by every list and detail view and by later modules (attendance, results).
  - Each relationship has object-level tests, allowed and denied.
  - Views answer 404 for objects outside the relationship.
- The existing role templates already name `students.student.view`, `students.child.view`, `students.profile.view_own` and `staff.profile.view_own`. Phase 7 defines them in the catalogue, so P7 syncs them.

## 9. Permissions (new codes, proposal)

- `students.student.view | view_assigned | manage | import | promote | transfer`
- `students.guardian.view | manage`
- `students.child.view`
- `students.profile.view_own`
- `students.document.view | upload`
- `staff.profile.view | manage | view_own`
- `staff.structure.manage` (departments and designations)
- `timetable.timetable.view | manage`
- `parent_portal.portal.use`

MFA is required for the manage, import, promote and transfer codes. Step-up is required for bulk promotion apply and import apply.

**Role templates:**

| Role | New permissions |
|---|---|
| owner, institution admin | all of the above in scope |
| academic coordinator | students view/manage/promote, timetable manage |
| admission officer | students view, manage, import (to complete enrollment) |
| teacher, class teacher | `students.student.view_assigned`, `timetable.timetable.view`, `staff.profile.view_own` |
| hr manager | staff profile view/manage, structure |
| guardian | `students.child.view`, `parent_portal.portal.use`, `timetable.timetable.view` (own children's units) |
| student | `students.profile.view_own`, `parent_portal.portal.use`, `timetable.timetable.view` (own unit) |

## 10. Platform operations (catalogue additions)

| # | Operation | Actor | Mechanism |
|---|---|---|---|
| P28 | Import housekeeping: delete import files and reports past retention | system | I |

The conversion handler runs as a tenant task (P26-style, no platform scope).

## 11. API and frontend

- **API:** `/api/v1/students/…`, `/api/v1/guardians/…`, `/api/v1/staff/…`, `/api/v1/timetable/…`, `/api/v1/portal/…` (tenant host, module-gated), plus OpenAPI and the generated client.
- **Frontend (en and bn, mobile-first):**
  - students list and profile (guardians, enrollment history, documents);
  - enroll and transfer, bulk promotion with preview;
  - the import wizard;
  - TC and ID card printing (template output, browser print);
  - staff directory and profile;
  - departments and designations;
  - the timetable grid editor with clash feedback;
  - the guardian/student portal with the child switcher;
  - the staff application-entry screen (a Phase 6 gap).

## 12. Milestones

| # | Scope |
|---|---|
| M1 | `students` data model: student, guardian, link, enrollment; RLS, composite keys, services, custom-field entities, numbering; isolation tests |
| M2 | Relationship scopes (selectors, permission codes, object-level tests); students and guardians API |
| M3 | `staff`: departments, designations, profiles, advisors; API; role templates |
| M4 | Admission → student conversion handler; enrollment from accepted applications; staff application-entry API |
| M5 | Lifecycle: transfer, withdraw, bulk promotion (preview, apply, rule suggestions), TC and alumni; ID cards and TC through templates |
| M6 | Bulk import (CSV and XLSX if approved): dry run, report, apply, P28 |
| M7 | `timetable`: periods, rooms, slots, clash constraints, views |
| M8 | Portal: invitations for guardians and students, child switcher, profile, enrollment, timetable, documents |
| M9 | Frontend for M1–M8 (en and bn) |
| M10 | E2E (admission → student → enrollment → timetable → guardian portal; import with errors; promotion), docs, security self-review |

## 13. Proposed ADRs

- **ADR-068:** students, guardians (N–N) and per-year enrollments in Phase 6 units. Documents through `files`. Status lifecycle with TC and alumni.
- **ADR-069:** portal access by invitation, linking memberships to guardian and student records. Phone-only guardians get records without logins until Phase 14.
- **ADR-070:** staff profiles optionally linked to memberships, departments and designations per institution, and unit advisors. Teaching stays keyed by memberships (ADR-063).
- **ADR-071:** basic timetable with constraint-backed clash detection. No substitutions or generator in Phase 7.
- **ADR-072:** bulk import with dry run, row-level report and atomic rows. CSV, plus XLSX through `openpyxl` if approved.
- **ADR-073:** relationship scopes (assigned, child, own) enforced in shared selectors and services, with object-level tests.

## 14. Questions for the owner

1. **Student numbering:** a Studio numbering sequence per institution (for example `STU-{YYYY}-{SEQ:5}`), editable by the tenant? **Recommendation:** yes.
2. **Phone-only guardians:** keep them as records without a login until SMS OTP sign-in (Phase 14, needs an SMS provider decision); or add phone OTP now? **Recommendation:** records now, OTP in Phase 14. An SMS provider needs a purchase or account decision that only you can make.
3. **XLSX import:** add `openpyxl` (pure Python, widely used, MIT-licensed) for Excel files, which most Bangladeshi offices use; or CSV only? **Recommendation:** add `openpyxl` and parse in read-only mode with size and row limits.
4. **Enrollment after admission:** create the student automatically on acceptance, and the enrollment when staff choose the section (automatic when the admitted unit has no children)? **Recommendation:** yes.
5. **ID cards and TC:** printable HTML from Studio templates now (browser print or save as PDF), and server-side PDF with Bengali and Arabic shaping in Phase 9 when the PDF engine is chosen? **Recommendation:** yes. A PDF engine is a separate dependency decision.
6. **Timetable scope:** periods, rooms, weekly slots and clash detection only; substitutions with attendance in Phase 8, no automatic generator? **Recommendation:** yes.
7. **Discipline notes:** the catalogue lists permission-restricted discipline notes. Defer them (they are sensitive data of minors and need a retention policy)? **Recommendation:** defer to a later phase with a retention decision.
8. **Duplicate guardians:** match by email or phone within the tenant when converting and importing, with a staff merge action? **Recommendation:** yes. Never match across tenants.

## 15. Exit criteria

- Object-level scope tests pass, allowed and denied, for each relationship:
  - teacher → assigned students;
  - guardian → own children only, including a guardian of two children in two institutions of the tenant;
  - student → self.
- An accepted application becomes a student with guardians and an enrollment, idempotently. A test covers this, and the E2E runs it through the real stack.
- The import's dry run reports row errors without writing anything. The apply creates exactly the valid rows. Limits are enforced, and exports are formula-safe.
- The timetable refuses teacher, room and unit clashes, including under concurrent writes.
- Every new tenant table has RLS and isolation tests. The URL audit, catalogue completeness, host-route review and migration rehearsal pass.
- Tests, lint, type checks, OpenAPI drift, E2E and CI all pass. The docs, progress file, decision log and security self-review are updated.

## 16. Implementation notes (appended during implementation)

### 16.1 M1 — students data model (2026-11-26, branch `feat/phase-07-m1`)

| # | Note |
|---|---|
| E1 | **New `students` app** (module `students`, standard, sellable; depends on `academics` and `customization`). Tables: `Student`, `Guardian`, `StudentGuardian` and `Enrollment`, all with standard RLS (`students.0002`, reversal refused). Composite keys keep an enrollment's student, year and unit in its institution, and every membership and guardian link in the tenant. The database refuses an enrollment in another institution's unit (tested) |
| E2 | **Numbers (ADR-074 Q1):** when the tenant defines the Studio sequence `student`, numbers are allocated from it, gap-free, inside the transaction. Otherwise staff give the number (letters, digits and `. / - _`, unique per institution) |
| E3 | **Guardians (ADR-074 Q8):** they are tenant-wide, because a guardian can have children in several institutions. Before creating one, the service matches by normalised phone (digits with an optional `+`) or lower-cased email, **within the tenant only** (RLS plus the tenant manager; tested). One primary guardian per student is enforced by a partial unique constraint. A merge moves links and the login to the kept guardian and needs `students.guardian.manage` in every affected institution |
| E4 | **Enrollments:** a leaf unit of the student's institution, an open year, a start date inside the year; at most one active enrollment per student and year, and unique roll numbers per unit (both partial unique constraints) |
| E5 | Custom-field entities `students.student` and `students.guardian`; file purpose `students.document` (PDF/JPEG/PNG, 10 MB, 30 per student, staff only). New plan limit key `max_active_students`, with a default of 0 (no limit) until plans set it (plan values are data, CLAUDE.md §8) |
| E6 | **Permissions:** 12 students codes (101 in total). Role templates: owner and institution admin get all staff codes; the academic coordinator gets view, manage and promote; the admission officer gets view, manage, import, guardians and documents; teachers and class teachers get **`view_assigned` only** (the class teacher's old `students.student.view` is replaced, ADR-073); the campus admin gets the view codes so they can assign teachers; guardian and student keep `students.child.view` and `students.profile.view_own`. The relationship selectors that give `view_assigned`, `child` and `own` their meaning arrive in M2. Until then those codes open nothing |
| E7 | Existing gates updated to the new facts: `students` is now built (the "unbuilt stays refused" tests use `fees`); 101 permission codes; the teacher's exact code set includes `view_assigned` |

### Change notes
- 2026-11-24 — Created (Proposed).
- 2026-11-26 — Approved by the owner with all recommended answers (ADR-074); ADR-068 to ADR-073 Accepted.
- 2026-11-26 — §16.1 appended: M1 notes E1–E7.
