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

### 16.2 M2 — relationship scopes and the students API (2026-11-26, branch `feat/phase-07-m2`)

| # | Note |
|---|---|
| E8 | **One selector for who sees which students** (`students.selectors.visible_students`). It unions four grounds, each needing its own permission:<ul><li>**scope:** `students.student.view` for the whole tenant, an institution, or a campus. Campus scope covers students actively enrolled in units of that campus.</li><li>**assigned:** `students.student.view_assigned` in the institution, held there or at one of its campuses. Covers students actively enrolled in a unit (or below it) that the member teaches through an offering of a year that isn't closed. Other modules add assignment sources through `STUDENTS_ASSIGNED_UNITS`; `staff` adds class-teacher advisors in M3.</li><li>**child:** `students.child.view`. Covers students linked to the guardian record whose login is the member.</li><li>**own:** `students.profile.view_own`. Covers the student's own record.</li></ul>Everything else answers 404, so a hidden student and an unknown one look the same |
| E9 | **Campus-scoped roles:** relationship checks accept the code held for the institution or for any of its campuses (`holds_in_institution`), because teacher and class-teacher roles are usually campus-scoped. **Defect found and fixed** by the object-level tests: the first version checked the institution only, so a campus-scoped teacher saw nobody |
| E10 | **Guardian contact details:** shown for all guardian links only with `students.guardian.view` in the student's institution. A guardian sees **only their own link**, never the other parent's details (for example after a separation). Custom-field values are masked by their view permission. The detail also says why the member sees the student (`staff`, `teacher`, `guardian`, `self`), so the UI can adapt |
| E11 | **API** (module `students`, tenant host):<ul><li>`students/` list (filters: institution, unit, status, name or number) and create;</li><li>`students/{id}/` detail and change;</li><li>`…/guardians/` link and unlink;</li><li>`…/enrollments/` enroll;</li><li>`guardians/` search (at least 3 characters; matches among visible students' guardians, plus the tenant's exact phone or email match, so staff find an existing guardian before creating a duplicate);</li><li>`guardians/merge/`.</li></ul>OpenAPI enum overrides were added for the student and enrollment statuses |
| E12 | **Object-level tests**, allowed and denied, for: owner (all); institution admin of another institution (only theirs); campus admin (the campus's enrolled students; another campus sees none); teacher (only the taught section; the other section is 404; no guardian details); guardian (own child only, own link only, cannot change); student (self only); another tenant (nothing) |

### 16.3 M3 — staff (2026-11-26, branch `feat/phase-07-m3`)

| # | Note |
|---|---|
| E13 | **New `staff` app** (module `staff`, standard, sellable; depends on `academics`). Tables: `Department` (per institution, optional parent, academic or administrative, archive), `Designation` (per institution, archive), `StaffProfile` and `UnitAdvisor`, all with standard RLS (`staff.0002`, reversal refused). Composite keys keep a profile's campus, department and designation, a department's parent, and an advisor's year, unit and staff profile in one institution (the database refuses a department or campus of another institution; tested) |
| E14 | **Profiles:** institution, optional home campus, number (Studio sequence `staff`, or given), names, gender, contact, joining date, status (active, on leave, inactive, left), employment type, department, designation, `extra` (entity `staff.profile`, masked by view permission). **The login is optional** (support staff often have none). A linked login is an active member of the tenant, with at most one profile per login and institution (a person may work at two institutions). Teaching stays keyed by memberships (ADR-063), so offerings needed no change |
| E15 | **Advisors (class teachers):** a staff member advises a unit for an academic year; one primary per unit and year (a new primary demotes the current one to assistant). Advising needs an active profile with an active login and an open year. Changing a profile to not active, or removing its login, ends its assignments in years that are not closed. **Assigning needs `academics.offering.manage`**, the same authority that assigns subject teachers (ADR-063), so the academic coordinator can do it as well as the head |
| E16 | **Advisor source of "the students I teach or advise":** `staff.selectors.advised_units` is registered in the new setting `STUDENTS_ASSIGNED_UNITS` next to `taught_units`. `students` loads the sources by path and never imports `staff`. Tested end to end: a campus-scoped class teacher who teaches nothing sees exactly the students of the advised section; advising a class covers its sections; a closed year or leaving shows nobody |
| E17 | **Who sees which profiles:** `staff.profile.view` for the tenant or an institution covers its profiles, and for a campus the profiles whose home campus it is; `staff.profile.view_own` (held in any scope) covers the member's own profiles. Everything else answers 404 |
| E18 | **Permissions:** 4 staff codes (105 in total). Role templates: owner and institution admin get all four; the campus admin gets view and view_own; the HR manager gets view, manage and structure; the academic coordinator gets view (to choose teachers and advisors); teachers and class teachers get `view_own` (`staff_member` already named it). The campus and institution admins hold `view_own` because nobody grants a code they don't hold |
| E19 | **API** (module `staff`, tenant host): `staff/` list (filters: institution, department, designation, status, name or number) and create; `staff/{id}/` detail (with the units the member advises and why it is visible: `staff` or `self`) and change; `staff/departments/` and `staff/designations/` per institution (list, create, change, archive); `staff/advisors/` per institution and year (list, assign) and `staff/advisors/{id}/` (remove). OpenAPI enum overrides for the staff status and the department kind |
| E20 | **Shared person validation:** the validation of a person's core values (name, names per language, email, phone, dates, gender) moved from `students.services` to `core.people`, so students, guardians and staff share one implementation (no behaviour change; the students tests are unchanged) |

### 16.4 M4 — admission → student (2026-11-26, branch `feat/phase-07-m4`)

| # | Note |
|---|---|
| E21 | **Conversion hook:** `students.conversion.on_application_accepted` is registered in `ADMISSIONS_ACCEPTED_HANDLERS`. After the acceptance commits it queues the tenant task `students.convert_application` (module `students`: refused for tenants without it, so their admissions work exactly as before; tested). `students` reads the application through the new `admissions.selectors.accepted_application`, not admissions tables, and admissions never imports `students` |
| E22 | **What is created:** the student (name, email, phone, date of birth; a value that doesn't validate for a student is left out rather than failing the conversion), custom values whose keys are student fields, the primary guardian from `guardian_name` / `guardian_phone` (matched by phone within the tenant first, ADR-074 Q8), and the enrollment **at once when the admitted unit has no units below it and the year is open**; otherwise staff choose the section later with the M2 enroll endpoint (ADR-074 Q4) |
| E23 | **Numbers:** the Studio `student` sequence when defined; otherwise the application number when free; otherwise `APP-` and the end of the application id (unique) |
| E24 | **Idempotent and safe:** one student per application (the M1 partial unique constraint, plus a concurrent-insert guard). The admission decision (`admissions.application.decide`) authorises the system conversion. A conversion that fails validation, for example the plan's student limit, is audited (`students.student.conversion_failed`, reason only) and leaves the application accepted |
| E25 | **Staff retry:** `POST students/from-application/` (`students.student.manage` in the application's institution, exact scope re-checked in the service) runs the same conversion: 201 when it creates the student, 200 when it already exists, 400 with the reason when it still can't, 404 for an application that isn't accepted or is outside the member's institutions |
| E26 | **Staff application entry:** the API already exists since Phase 6 M4 (`POST admissions/applications/`, `admissions.application.review`, validated by the cycle's form). No change was needed; the screen remains a UI gap for M9 |
| E27 | **Internal service helpers:** `insert_student`, `find_or_create_guardian`, `attach_guardian` and `insert_enrollment` hold the validation and inserts without the permission check; the public services authorise and then call them, so the conversion reuses exactly the same rules |

### 16.5 M5 — lifecycle (2026-11-26, branch `feat/phase-07-m5`)

| # | Note |
|---|---|
| E28 | **Move within the year** (`students.student.manage`): the active enrollment ends as `transferred` and a new one starts in another leaf unit of the same year (history kept) |
| E29 | **Withdraw** and **transfer certificate** (`students.student.transfer`): only active students; active enrollments end; the student becomes `withdrawn` or `transferred`. New table `students_transfercertificate` (number unique per institution, reason, destination, date; standard RLS, composite keys, `students.0003`/`0004`). Numbers come from the Studio sequence `transfer_certificate`, or staff give one. Free-text reasons never go into the audit log |
| E30 | **Promotion** (`students.student.promote`; the API needs a fresh step-up, tested): a preview lists the active enrollments of a source unit and year with a suggestion. The published `academics.promotion` rule, when named, suggests promote (true) or repeat (false) from `student.*` (core fields and custom values) and `today`; a failing rule suggests repeat with a note. Without a next unit every suggestion is *complete* (the final level). Staff send their decisions; applying is **one transaction**: any invalid decision rolls back everything (tested). Promote and repeat start the next year's enrollment (target unit or the same unit); the old one ends as promoted or repeated |
| E31 | **Alumni:** completing the final level makes the student `alumni` (ADR-068) |
| E32 | **Printable documents (ADR-074 Q5):** two template kinds, `students.id_card` and `students.transfer_certificate` (HTML, sandboxed and autoescaped, ADR-056). Rendering needs `students.student.view` in the student's institution and a published template **of that kind** (another kind is refused). The API returns the HTML for the browser to print; server PDF arrives in Phase 9 |
| E33 | **API:** `students/{id}/move/`, `…/withdraw/`, `…/transfer-certificates/` (list, issue), `…/transfer-certificates/{tc}/document/`, `…/id-card/`, `students/promotion/preview/` and `students/promotion/apply/` |

### 16.6 M6 — bulk import (2026-11-26, branch `feat/phase-07-m6`)

| # | Note |
|---|---|
| E34 | **Flow:** upload through `files` (new purpose `students.import`: CSV or XLSX, 5 MB, the uploader's own verified file), `POST imports/` with the institution, kind, column mapping (column → field, `extra.<key>` for custom fields) and options; a **dry run** is queued at once. The tenant task `students.run_import` reads the file in the task body (new bounded `files.storage.read` / `files.services.read_content`) and runs every row through the same services staff use, each in its own savepoint; the dry run rolls every row back (tested: nothing is written). `POST imports/{id}/apply/` runs it for real: each valid row is created, each failure is reported, nothing else is affected |
| E35 | **Kinds** (setting `STUDENTS_IMPORT_KINDS`, loaded by path): `students` (core fields, custom fields, the primary guardian, and the enrollment by unit code in the job's academic year) and `staff` (profiles with department and designation by code, from `staff.imports`). Permissions: `students.student.import` (MFA and **step-up**, tested at the API) or `staff.profile.manage`, checked by the same permission class and again in the exact institution by the service. The import endpoints sit in the `students` module, so a tenant imports staff only with `students` entitled (recorded as a known limitation) |
| E36 | **Limits and safety:** 5 000 rows and 60 columns; UTF-8 CSV; XLSX through `openpyxl` read-only, first sheet, refused when its uncompressed size exceeds 40 MB or 100× the file (zip bombs). Python 3.13's expat already limits entity expansion. Every rule, including `max_active_students`, is enforced row by row by the services. Custom values are converted to their field types (whole numbers, yes/no, `;`-separated choices) |
| E37 | **Report:** one entry per row (line number, ok, errors by field, created id) in the job; `GET imports/{id}/report/` downloads it as CSV with formula-looking cells neutralised (`'=…`). Jobs are visible to their starter or to holders of the kind's permission in the institution (others: 404) |
| E38 | **P28 (catalogue, mechanism I):** `students.import_housekeeping` (daily) fans out `students.purge_imports` per active or suspended tenant: jobs older than 30 days are deleted (reports hold personal data) and their files marked deleted (P27 removes the objects) |
| E39 | **New dependency `openpyxl` 3.1.5** (MIT, with `et-xmlfile`), approved by ADR-074 Q3; mypy treats it as untyped. The XLSX content type joins the files safe-type list (always served as an attachment) |

### 16.7 M7 — timetable (2026-11-26, branch `feat/phase-07-m7`)

| # | Note |
|---|---|
| E40 | **New `timetable` app** (module `timetable`, standard, sellable; depends on `academics` and `staff`). Tables `BellSchedule`, `Period` (ordered, non-overlapping within a schedule; breaks take no lessons), `Room` (per institution, optional campus, capacity) and `Slot` (year and term from the offering, unit, weekday 1–7, period, offering, teacher, room); standard RLS and composite tenant/institution keys (`timetable.0002`, reversal refused) |
| E41 | **Clash detection (ADR-071):** unique constraints refuse a second lesson for the same unit, teacher or room in the same year, term, weekday and period, so concurrent writers can't double-book (tested directly against the database; a lost race is reported as the clash). The service also refuses what the constraints can't see: an overlapping period of **another bell schedule**, and a **whole-year lesson against a term's lesson** (tested) |
| E42 | **Teachers:** a slot's teacher must teach the offering (Phase 6 offering teachers, ADR-063): the primary teacher by default, another of its teachers, or none yet |
| E43 | **Who sees what:** staff (`timetable.timetable.view` and `academics.structure.view` in the institution or one of its campuses) see any unit's, room's or teacher's timetable; guardians and students see only units their children or they are actively enrolled in (`TIMETABLE_PORTAL_UNITS`, provided by `students.selectors.portal_units`; `timetable` never imports `students`); `timetable/my/` lists the lessons a member teaches. Everything else answers 404 (tested: another section, a room, staff lists, another tenant) |
| E44 | **Permissions:** `timetable.timetable.view` and `timetable.timetable.manage` (MFA); 107 codes in total. Role templates: owner and institution admin both; academic coordinator both (manage was already named); campus admin view; teachers, class teachers, guardians and students view |
| E45 | **API:** `timetable/schedules/` (list with periods, create), `timetable/schedules/{id}/periods/`, `timetable/rooms/`, `timetable/slots/` (by unit, room or teacher; create), `timetable/slots/{id}/` (remove) and `timetable/my/`. Not in Phase 7 (ADR-074 Q6): substitutions and automatic generation |

### 16.8 M8 — portal invitations and the portal (2026-11-26, branch `feat/phase-07-m8`)

| # | Note |
|---|---|
| E46 | **Portal invitations (ADR-069):** `POST guardians/{id}/invite/` (`students.guardian.manage` in every institution where the guardian has a child) and `POST students/{id}/invite/` (`students.student.manage`) use the Phase 3 invitation flow unchanged: the tenant's system role `guardian` or `student`, granted in the student's institution, so `create_invitation` checks `tenancy.member.invite` and that the inviter holds every code of the role (no escalation). New table `students_portalinvite` (invitation, kind, record, linked time; standard RLS). An email address is required; phone-only guardians stay without a login until phone sign-in (ADR-074 Q2) |
| E47 | **Linking on acceptance:** a new tenancy hook, `TENANCY_INVITATION_ACCEPTED_HANDLERS`, runs inside the acceptance transaction (both the signed-in and the password paths); `students.portal.on_invitation_accepted` links the membership to the guardian or student record once. A record that got another login meanwhile, or a login already linked to another record of that kind, is left alone. One account serves several children; a guardian who is also staff keeps one account |
| E48 | **Relationship codes in any scope:** `students.child.view` and `students.profile.view_own` now count when held in any scope of the tenant (`holds_anywhere`), because invited guardians and students hold their role in an institution. They still only open the member's children or own record |
| E49 | **Role templates:** owner and institution admin also hold `students.child.view`, `students.profile.view_own` and `parent_portal.portal.use`, so they can invite guardians and students (nobody grants a code they don't hold); these codes open nothing else for them. Guardian and student templates gain `parent_portal.portal.use` |
| E50 | **New `parent_portal` module** (no tables; permission `parent_portal.portal.use`; 108 codes in total): `portal/children/` (the switcher: children or oneself, the relation, the current enrollment) and `portal/children/{id}/` (profile, enrollment and the unit's timetable when the tenant has `timetable`). Only the child and own grounds apply, never staff scope, so a teacher who is a parent sees only their children in the portal (tested: staff get an empty list and 404) |
| E51 | **Not yet:** guardian-visible student documents. Student documents have a file purpose (M1) but no upload API or guardian visibility flag yet; recorded as a known gap. Attendance, results, fees and notices plug into the portal in Phases 8–14 |

### 16.9 M9 — frontend (2026-11-27, branch `feat/phase-07-m9`)

| # | Note |
|---|---|
| E52 | **Students** (`/students`, `/students/{id}`): the list the server allows (search by name or number, per institution), creation (number from the Studio sequence or given), and the detail with why it is visible (staff, you teach or advise, your child, you), the profile, enrollments (enroll in a leaf unit of an open year, or move within the year), guardians (link with phone/email matching, primary, unlink, portal invitation), and actions (withdraw, transfer certificate, portal invitation, ID card and transfer certificate previews from Studio templates in a **sandboxed iframe**, no scripts) |
| E53 | **Promotion** (`/students/promotion`): choose the source unit and year and the next year (and unit, or none for the final level), an optional promotion rule; preview the suggestions, change any decision, apply in one transaction (step-up handled by the shared action helper) |
| E54 | **Import** (`/students/import`): kind (students or staff, by permission), upload through `files` (shared presigned-upload helper, now also used by the applicant status page), wait for verification, map columns (suggested from the CSV header read in the browser; typed for XLSX), the year for enrollments, the dry run with the row errors, apply, and the formula-safe report download |
| E55 | **Staff** (`/staff`): directory (login optional), creation with department, designation and employment type, departments and designations, and class teachers (assign and remove; staff with a login only) |
| E56 | **Timetable** (`/timetable`): a unit's week as a grid (rows by start time, columns by day), "my lessons", and for managers bell schedules with periods and breaks, rooms, and adding or removing lessons (clashes refused by the server) |
| E57 | **Portal** (`/portal`): the child switcher and the chosen child's class and week (read-only) |
| E58 | **Staff application entry** (the Phase 6 gap): "Enter an application" on an open cycle renders the cycle's Studio form for staff through two new endpoints, `admissions/cycles/{id}/form/` and `…/visibility/` (`admissions.application.review` in the cycle's institution; tested allowed and denied), and submits to the existing staff endpoint |
| E59 | **Navigation** gains Students, Staff, Timetable and My children, each shown only with its permission and its module. **API schema fix:** the bell schedule's `periods` are now typed in OpenAPI (they were untyped), so the client is typed end to end. All strings are in English and Bengali |

### Change notes
- 2026-11-24 — Created (Proposed).
- 2026-11-26 — Approved by the owner with all recommended answers (ADR-074); ADR-068 to ADR-073 Accepted.
- 2026-11-26 — §16.1 appended: M1 notes E1–E7.
- 2026-11-26 — §16.2 appended: M2 notes E8–E12.
- 2026-11-26 — §16.3 appended: M3 notes E13–E20.
- 2026-11-26 — §16.4 appended: M4 notes E21–E27.
- 2026-11-26 — §16.5 appended: M5 notes E28–E33.
- 2026-11-26 — §16.6 appended: M6 notes E34–E39.
- 2026-11-26 — §16.7 appended: M7 notes E40–E45.
- 2026-11-26 — §16.8 appended: M8 notes E46–E51.
- 2026-11-27 — §16.9 appended: M9 notes E52–E59.
