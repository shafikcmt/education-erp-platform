# Phase 8 Plan — Attendance Management

- **Status:** **Approved** (owner, 2026-11-28: "approval all ur recommended and continur develop same") with the recommended answers to Q1–Q9 (ADR-081). ADR-076 to ADR-080 Accepted.
- **Depends on:**
  - Phase 7 (**Approved** by the owner, 2026-11-28; ADR-068 to ADR-075).
  - Accepted ADRs:
    - tenancy and isolation: ADR-009, ADR-043, ADR-046;
    - modules and entitlements: ADR-050 to ADR-054;
    - Customization (settings, rules, workflows, templates): ADR-055 to ADR-062;
    - academics and files: ADR-063, ADR-064;
    - students, staff, timetable and relationship scopes: ADR-068 to ADR-074.
- **Roadmap scope (`DEVELOPMENT_ROADMAP.md` Phase 8):**
  - daily and period attendance, mobile quick-mark UI;
  - edits with audit, and a permission for past dates;
  - staff attendance;
  - leave requests through workflows;
  - thresholds;
  - absence alert events (minimal in-app and email now; full delivery in Phase 14);
  - attendance reports;
  - the device-integration API design (implementation optional).
- **Roadmap exit criteria:** a teacher marks attendance on a phone in the E2E; a partition strategy for `attendance_record` is evaluated.
- **Requirements:**
  - ATT-01 (daily and period student attendance, mobile-friendly), ATT-02 (staff attendance and leave), ATT-05 (thresholds and reports): Phase 8;
  - ATT-03 (absence alerts): in-app and email now, SMS in Phase 14;
  - ATT-04 (device integration, *could*): API design only (see Q6);
  - ATT-05 advanced dashboards: Phase 15.
- **Model sketch already in the docs:** `DATABASE_DESIGN.md` §2.7 (`attendance_session`, `attendance_record`, `attendance_leaverequest`). This plan refines it.

## 1. Goals

1. **One attendance engine for every institution type.**
   - A school takes one daily register per section.
   - A university takes attendance per course lecture.
   - A coaching centre takes it per batch class.
   - A madrasa may take several registers a day; hostel roll-calls arrive in Phase 12 on the same engine.
   - The mode is configuration (a Studio setting from the preset), not code per type.
2. **Fast on a phone.** A teacher opens today's class, everyone starts as present, taps the absentees and submits. A 40-student class should take under a minute.
3. **Trustworthy records.**
   - Who marked what, and every later change with its reason, is audited.
   - Past dates are editable only within a configurable window, or with a separate permission.
   - Two people marking the same register cannot silently overwrite each other.
4. **Relationship scopes reused (ADR-073).** A teacher marks and sees only the units and offerings they teach or advise. A guardian sees only their children's attendance. A student sees only their own.
5. **Useful outputs.** Guardians are told the same day when a child is absent. Class teachers see who is below the attendance threshold. Staff get daily, monthly and per-student reports with formula-safe CSV export.
6. **The same guarantees as every phase:** RLS on every tenant table; permissions in views and services; module entitlement on every route; isolation tests; en and bn; mobile-first; tenant hosts stay disabled.

## 2. Data model (proposed ADR-076)

All tables are tenant-owned, with standard RLS (ENABLE + FORCE) and composite tenant/institution keys, as in Phases 6–7.

- **`attendance_session`** — one register:
  - institution, campus (from the unit), academic year, term (where semester-based);
  - unit (the leaf the students sit in), date;
  - kind `daily | period` (`hostel_rollcall` is reserved for Phase 12; `staff_daily` is in §5);
  - for period registers: the offering, and the timetable slot or period when one exists;
  - taken by (membership), submitted at, status `open | submitted | locked`;
  - a `version` integer for optimistic concurrency.
  - **Uniqueness:** one daily register per unit and date; one period register per unit, date and period (or offering and date when there is no timetable). Partial unique constraints make a duplicate register impossible, even for concurrent writers.
- **`attendance_record`** — one row per student per register:
  - session, student, status (§3), late minutes (optional), remark (short, optional);
  - `date` and `institution` copied from the session, so reports and a later partitioning (§10) need no join;
  - unique (session, student).
- **`attendance_leaverequest`** — see §6.
- **`attendance_staffrecord`** — see §5.
- **Indexes:** (tenant, institution, date), (tenant, student, date) and (tenant, unit, date). Monthly reports and the portal read by student and date range.
- **Roster:** the students of a register are the active enrollments of its unit and year on that date (Phase 7). A student enrolled or moved mid-year appears only from that date. Records are never created for students outside the unit.

## 3. Statuses and modes (Studio settings)

- **Fixed status categories** that the engine computes with: `present`, `absent`, `late`, `excused`, `leave`.
  - Present and late count as attended.
  - Excused and leave are not counted against the student.
  - Absent counts against.
- **Labels are configuration.** A tenant can rename them in Studio terminology (for example, Bengali labels or "On duty" for excused). No tenant can add a category the engine does not understand.
- **New Studio settings** (namespace `attendance`, resolved Core → preset → tenant → institution → campus):

| Setting | Default | Meaning |
|---|---|---|
| `attendance.mode` | from the preset: school, madrasa and college `daily`; university `period`; coaching and training `period` | `daily`, `period` or `both` |
| `attendance.default_status` | `present` | what the quick-mark screen starts with |
| `attendance.edit_window_days` | `3` | days after the date during which the marker may still edit; later edits need `attendance.record.manage` |
| `attendance.lock_after_days` | `30` | registers lock automatically; unlocking needs `attendance.record.manage` and a reason |
| `attendance.threshold_percent` | `75` | below this, a student is flagged (§7) |
| `attendance.alert_guardians` | `true` | absence alerts to guardians with portal logins |
| `attendance.alert_email` | `false` | also email those alerts |
| `attendance.late_after_minutes` | none | optional; only a label hint, no automatic status |

- Preset files gain the `attendance` block in a **v3 preset version**. Presets stay immutable and opt-in (ADR-058); tenants on v1 or v2 keep the core defaults until they adopt v3.

## 4. Marking and editing (proposed ADR-077)

- **Who may mark:**
  - `attendance.record.mark`: only registers of units the member advises (daily) or offerings the member teaches (period) in that year. This reuses the Phase 7 assigned-units selector (`STUDENTS_ASSIGNED_UNITS`).
  - `attendance.record.manage` (MFA): any register in the member's institution or campus scope. This is for coordinators, and for covering an absent teacher.
- **Flow:**
  1. Open (or create) today's register. The server returns the roster with each student's current status, and today's approved leave pre-filled as `leave`.
  2. Save in one request: the whole list of `{student, status, remark}` with the register's `version`. A stale `version` returns **409** with the current state. The UI shows who changed it and lets the user re-apply.
  3. Submit. This sets `submitted_at` and fires the after-commit absence alerts (§7).
- **Editing:**
  - Same day, and up to `edit_window_days`: the marker can edit.
  - After that: `attendance.record.manage` only, with a **mandatory reason**.
  - Locked registers: editable only after an audited unlock.
  - Future dates cannot be marked.
- **Audit:** each save records one audit event per register (`attendance.register.saved`) with the changed students and their old and new statuses. Changes after submission carry the reason. Audit metadata uses ids, never names.
- **Not in Phase 8:** offline marking on the device (see Q4).

## 5. Staff attendance

- **`attendance_staffrecord`:** staff profile, date, status (the same categories), check-in and check-out times (optional), remark, marked by. Unique (profile, date).
- Marked per campus by members with `attendance.staff.mark` (MFA), for example HR or the front desk, as a daily register.
- Staff see their own attendance (`staff.profile.view_own`, Phase 7).
- **Approved staff leave** (§6) pre-fills `leave`.
- **Not in Phase 8:** leave types and balances, and payroll links (Phase 11, `hr_payroll`); self check-in by phone or location; device punches (§9).

## 6. Leave requests (through Phase 5 workflows)

- **`attendance_leaverequest`:**
  - the person: a student (requested by a guardian, the student, or staff on their behalf) or a staff profile (requested by themselves);
  - from and to dates, an optional half-day flag, a reason, an optional attachment (`files`, purpose `attendance.leave`, ADR-064);
  - status `pending | approved | rejected | cancelled`;
  - the workflow instance.
- **Approval** uses the Phase 5 workflow engine with a declared subject `attendance.leave_request`.
  - If the tenant has published a workflow for that subject, it is used (multi-step chains, guards, SLA, notifications).
  - Otherwise a built-in single step applies: `pending → approved | rejected` by `attendance.leave.review` in the person's institution (class teacher or coordinator for students, HR for staff).
- **Effect:** approved leave pre-fills `leave` on those dates in open registers and on registers created later. It never overwrites a status already saved, and the conflict is shown to the marker.
- **Who can request:**
  - guardians for their children (`students.child.view` + `attendance.leave.request`);
  - students for themselves (`students.profile.view_own` + `attendance.leave.request`);
  - staff for themselves (`staff.profile.view_own` + `attendance.leave.request`);
  - staff with `attendance.leave.review` on behalf of a student in scope.

## 7. Absence alerts and thresholds (minimal now, ADR-078)

- **Absence alerts (ATT-03):**
  - When a register is submitted, a tenant task runs after commit.
  - For each absent student, the guardians with `receives_notices` and a portal login get an **in-app notification** (`notifications_core`). An email is added when `attendance.alert_email` is on.
  - At most one alert per student per day, even when several period registers mark the same student absent.
  - Changing a student back to present on the same day does not send a correction in Phase 8. The portal always shows the current status.
  - **SMS** to phone-only guardians arrives in Phase 14 with the SMS provider (the owner's decision, ADR-074 Q2).
- **Thresholds (ATT-05):**
  - A student's attendance percentage = attended ÷ (registers taken − excused − leave) in a period. It is based on registers actually taken, so no holiday calendar is needed (see Q3).
  - Students below `attendance.threshold_percent` are flagged in reports and in the class teacher's view.
  - A new rule namespace **`attendance.flag`** (ADR-055 evaluator) lets a tenant write a stricter rule, for example "3 consecutive absences". Variables: `attendance.percent`, `attendance.absent_days`, `attendance.consecutive_absences`, `attendance.late_days`, and the student fields. It returns true/false.
  - **P29** (system, per-tenant iteration, nightly): evaluates flags and notifies each class teacher once per newly flagged student (in-app).
  - The `academics.promotion` namespace (Phase 6) gains `attendance.percent` for the year, as promised in Phase 7 §2.

## 8. Reports, portal and exports

- **Staff reports** (`attendance.report.view` in scope):
  - daily register status: which registers are taken, missing or late, per campus;
  - unit register for a month (students × days grid);
  - per-student summary with percentages over a date range;
  - unit and institution summaries;
  - staff monthly register.
- **CSV export** for each report, formula-safe. The Phase 7 import `safe_cell` helper moves to `core` so both modules share it (no duplicated code).
- **Printable monthly register** through a Studio template kind `attendance.monthly_register` (sandboxed, ADR-056), like ID cards in Phase 7. Server PDF arrives in Phase 9.
- **Portal (`parent_portal`):** each child's (or one's own) month calendar, percentage, flags and leave requests, with a leave-request form.
- **Teachers:** their own registers for today and the week, with a "missing" badge for registers not yet taken.

## 9. Device integration (ATT-04, design only — ADR-079)

- A written API design, `docs/ATTENDANCE_DEVICE_API.md`, covering:
  - device registration per campus (a device record, a hashed secret, an allowed IP list);
  - a signed event endpoint (`person reference, timestamp, direction`), idempotent by device event id;
  - mapping punches to staff records (and optionally to student daily registers);
  - clock-skew rules;
  - rate limits;
  - the audit trail.
- **Not implemented in Phase 8.** Device authentication is a machine credential, so it belongs to the token path of ADR-028, which is still Proposed. No vendor and no hardware are chosen.

## 10. Partition strategy for `attendance_record` (exit criterion, ADR-080)

- **Volume estimate** (an assumption to be measured, not research):
  - a 2 000-student school with daily registers over 220 school days ≈ 0.44 M rows a year;
  - in period mode with 6 periods, ≈ 2.6 M rows a year per tenant;
  - with 500 such tenants: 0.2–1.3 billion rows a year in one shared table.
- **Phase 8 decision (proposed): no partitioning yet, but partition-ready.**
  - `attendance_record` carries `date` and `institution`, and every index starts with `tenant_id`.
  - Reports always filter on a date range.
  - The primary key stays a UUIDv7 id. Converting later to monthly range partitions on `date` requires the key to include `date`. That is an expand → migrate → contract change, and it is documented in the ADR.
  - **Trigger to partition:** the table passes 50 M rows, or index-only report queries exceed 200 ms at p95 in the Phase 18 benchmark (together with the D9 benchmark, ADR-049).
  - The evaluation (estimates, query plans on generated data, the migration path, and how RLS applies to partitions) is written in the ADR and in `DATABASE_DESIGN.md`. A query-plan check runs on 5 M generated rows during M7.

## 11. Permissions (new codes, proposal)

| Code | Purpose | MFA |
|---|---|---|
| `attendance.record.mark` | mark registers of assigned units and offerings | |
| `attendance.record.view` | view registers in institution or campus scope | |
| `attendance.record.manage` | mark any register in scope, edit past the window, unlock | yes |
| `attendance.report.view` | reports and exports in scope | |
| `attendance.staff.mark` | staff daily register | yes |
| `attendance.staff.view` | staff attendance in scope | |
| `attendance.leave.request` | request leave for oneself or one's children | |
| `attendance.leave.review` | approve or reject leave in scope | |

Step-up is required for unlocking a register and for edits outside the edit window. With these 8 codes the catalogue grows from 108 to 116. The `teacher` and `class_teacher` templates already name `attendance.record.mark`.

**Role templates:**

| Role | New permissions |
|---|---|
| owner, institution admin | all |
| campus admin | all in campus scope |
| academic coordinator | record view/manage, report view, leave review |
| teacher | record mark (already listed), leave request |
| class teacher | record mark, record view (own units through the scope), leave review (own units' students), leave request |
| hr manager | staff mark/view, leave review (staff), report view |
| front desk | staff mark |
| guardian, student | leave request (their own attendance is read through the child/own codes) |
| staff member | leave request |

## 12. Platform operations (catalogue additions)

| # | Operation | Actor | Mechanism |
|---|---|---|---|
| P29 | Attendance nightly: lock registers past `lock_after_days`, evaluate flags, notify class teachers | system | I |

Absence alerts run as tenant tasks (no platform scope).

## 13. API and frontend

- **API** (tenant host, module-gated `attendance`):
  - `/api/v1/attendance/registers/` (today's and a date's registers for the caller), `…/{id}/` (roster with statuses), `…/{id}/save/`, `…/{id}/submit/`, `…/{id}/unlock/`;
  - `/api/v1/attendance/staff/…` (daily staff register);
  - `/api/v1/attendance/leave/…` (request, list, cancel, decide);
  - `/api/v1/attendance/reports/…` (each report and its CSV);
  - `/api/v1/portal/children/{id}/attendance/` (portal);
  - OpenAPI and the generated client.
- **Frontend (en and bn, mobile-first):**
  - teacher "Today" screen: the day's registers with status badges;
  - **quick-mark screen:** a large tap target per student, all present by default, one tap cycles absent → late → present, a sticky Save/Submit bar, a 409 conflict dialog;
  - register edit with reason, unlock;
  - staff daily register;
  - leave requests (portal form; staff review queue);
  - reports with filters and CSV download; the printable monthly register;
  - portal attendance calendar.

## 14. Milestones

| # | Scope |
|---|---|
| M1 | Data model: sessions, records, staff records, leave requests; RLS, composite keys; settings and statuses; v3 presets; isolation tests |
| M2 | Marking services and API: registers, roster, save with optimistic concurrency, submit, edit window, lock and unlock, audit; scope tests (assigned, manage) |
| M3 | Leave requests: workflow subject, built-in single step, pre-fill and conflicts, attachments |
| M4 | Staff attendance register and staff leave |
| M5 | Absence alerts, the `attendance.flag` namespace, P29, promotion variable |
| M6 | Reports, CSV, the monthly register template, portal endpoints; `safe_cell` moved to core |
| M7 | Partition evaluation (generated data, query plans, ADR text) and the device API design document |
| M8 | Frontend for M1–M6 (en and bn) |
| M9 | E2E (a teacher marks on a mobile viewport; a guardian sees the absence alert and requests leave; reports), docs, security self-review |

## 15. Proposed ADRs

- **ADR-076:** attendance registers (sessions) per unit, date and kind, with per-student records; fixed status categories with configurable labels; mode by Studio setting from the preset (v3 presets).
- **ADR-077:** marking by relationship scope (assigned units and offerings) or the `manage` permission; optimistic concurrency with a register version; an edit window, auto-lock and audited unlock; one audit event per save.
- **ADR-078:** absence alerts in-app (and optional email) to guardians with portal logins, once per student per day; a percentage over registers taken; the `attendance.flag` rule namespace and the P29 nightly job.
- **ADR-079:** the device integration API is designed, not built, until a machine-credential path (ADR-028) is accepted.
- **ADR-080:** `attendance_record` is partition-ready (date copied onto the row, tenant-first indexes) but not partitioned until a measured trigger; the evaluation is recorded.

## 16. Questions for the owner

1. **Default modes per institution type:** school, college and madrasa daily; university, coaching and training per period/class, each changeable in Studio? **Recommendation:** yes.
2. **Edit window and lock:** the marker can edit for 3 days; after that only `manage` with a reason; registers lock after 30 days. Both values are tenant settings. **Recommendation:** yes, with these defaults.
3. **Percentage base:** count only registers actually taken (no holiday calendar in Phase 8); an academic calendar with holidays later, when examinations or reports need it? **Recommendation:** yes. It avoids a calendar module now and never counts a holiday as an absence.
4. **Offline marking:** marking needs a connection in Phase 8. The screen keeps unsaved marks in memory and retries, but stores nothing on the device (it would put minors' data in browser storage). Full offline sync later, if field data shows it is needed? **Recommendation:** yes.
5. **Absence alerts:** in-app for guardians with portal logins now, email as a tenant option (off by default), SMS in Phase 14 after you choose an SMS provider? **Recommendation:** yes. An SMS provider needs a purchase or account decision that only you can make.
6. **Device integration:** a written API design only in Phase 8; building it waits for the machine-credential decision (ADR-028) and a real device to test with? **Recommendation:** yes.
7. **Staff leave:** requests and approval now, without leave types or balances (they come with HR in Phase 11)? **Recommendation:** yes.
8. **Timetable substitutions:** cover for an absent teacher is done by a coordinator marking with `manage`; a substitution feature waits for a later phase? **Recommendation:** yes, keep Phase 8 focused on attendance.
9. **Partitioning:** not now, partition-ready, with the trigger and benchmark in Phase 18 (§10)? **Recommendation:** yes.

## 17. Exit criteria

- A teacher marks a register on a **mobile viewport** in the real-stack E2E: open today, tap absentees, submit. The guardian of an absent child sees the in-app alert in the portal.
- Scope tests, allowed and denied:
  - a teacher marks only assigned units and offerings;
  - `manage` marks any register in scope;
  - a guardian sees only their children; a student sees only themselves;
  - 404 for hidden registers and students.
- Concurrency: two saves with the same version, one wins and one gets 409; duplicate registers are impossible (tested against the database).
- The edit window, lock and unlock with reason are enforced and audited. Future dates are refused.
- Leave: the built-in step and a published workflow both work; approved leave pre-fills without overwriting saved statuses.
- Reports match hand-computed percentages for a fixture, and CSV export is formula-safe.
- The partition evaluation is written (ADR-080, `DATABASE_DESIGN.md`) with query plans on generated data.
- Every new tenant table has RLS and isolation tests. The URL audit, catalogue completeness, host-route review and migration check pass.
- Tests, lint, type checks, OpenAPI drift, E2E and CI all pass. The docs, progress file, decision log and security self-review are updated.

## 18. Implementation notes (appended during implementation)

### 18.1 M1 — data model (2026-11-28, branch `feat/phase-08-m1`)

| # | Note |
|---|---|
| A1 | New `apps/attendance`: `Register`, `Record`, `StaffRecord`, `LeaveRequest`; migrations `0001_initial` and `0002_keys_rls` (composite tenant/institution keys, standard RLS on the four tables, reversal refused) |
| A2 | **Naming deviation:** the plan's `attendance_session` table is `attendance_register` (model `Register`), to avoid confusion with login sessions. `DATABASE_DESIGN.md` §2.7 is updated |
| A3 | **Period registers are keyed by offering, date and `sequence`** (several lectures of one offering on a day), not by a timetable period: `timetable` is not a dependency of `attendance`, so the slot is kept by id only (`slot_ref`). One daily register per unit and date. Both are partial unique constraints |
| A4 | A record's `date` and `institution` are kept equal to its register's by a composite key on `(tenant, institution, register, date)` (ADR-080); a record's student must belong to the register's institution. Late minutes only with the `late` status |
| A5 | Leave requests: exactly one person (student or staff), end ≥ start, half days on one date only. The attachment column arrives with M3 (attachments through `files`) |
| A6 | Settings declared by the `attendance` manifest: `mode`, `default_status`, `edit_window_days` (3), `lock_after_days` (30), `threshold_percent` (75), `alert_guardians` (on), `alert_email` (off); read in one place (`attendance/config.py`). **Deviation:** `late_after_minutes` (a label hint only) is not added, because nothing would use it |
| A7 | **v3 presets** for the six types: v2 plus `attendance.mode` (daily: school, college, madrasa; period: university, coaching, training); v3 is the default for new institutions, v2 stays for existing ones (opt-in, ADR-058). The university v3 preset also suggests `attendance` |
| A8 | 8 permission codes (116 in total) and role templates as in §11. **Deviation:** the class teacher does not get `attendance.record.view` (an institution- or campus-wide code); their view comes from the assigned scope of `attendance.record.mark`. Their `attendance.leave.review` is narrowed to their own units in M3 |

### 18.2 M2 — marking services and API (2026-11-28, branch `feat/phase-08-m2`)

| # | Note |
|---|---|
| A9 | `attendance/selectors.py`: who may mark (class teacher of the unit or a unit above it for daily registers; teacher of the offering for period registers; both need `attendance.record.mark` in the institution or a campus), manage (`attendance.record.manage` at the institution or the register's campus) and view; the roster (students whose enrollment covers the date, through the new `students.selectors.unit_roster`); approved leave pre-filled; the teacher's work list (`due_for`) |
| A10 | `attendance/services.py`: open (idempotent; the mode, future dates, open year and leaf unit are checked), save with the register `version` (stale → 409 `stale_register`, nothing changes), submit (every roster student needs a status), unlock (manager, reason), `lock_due` for P29. Students outside the roster and duplicate entries are refused |
| A11 | **Edit window:** within `edit_window_days` the marker edits; later only `attendance.record.manage`, with a reason, MFA and a fresh step-up at the API. Locked registers refuse saves until unlocked. **Unlock lasts until the nightly lock (P29, M5) runs again**: it is meant for a correction, not to reopen a month |
| A12 | Audit events `attendance.register.opened/saved/submitted/unlocked` carry ids, dates, statuses (`"<student>:<old>><new>"`, at most 50, plus a count) and whether a reason was given; reasons and remarks are never logged |
| A13 | API (tenant host, module `attendance`): `attendance/due/`, `attendance/registers/` (list per institution and date; open), `…/{id}/` (roster), `…/{id}/save/`, `…/{id}/submit/`, `…/{id}/unlock/`. Hidden registers answer 404; the routes are in the host-route review. `ATTENDANCE_SUBMITTED_HANDLERS` (empty) is ready for the M5 alerts |
| A14 | **Not in M2:** the leave workflow (M3), staff registers (M4), alerts and P29 scheduling (M5), the frontend (M8). Concurrent saves are serialised by `select_for_update` on the register and the version check; a threaded concurrency test is deferred to M9 with the E2E |

### 18.3 M3 — leave requests (2026-11-28, branch `feat/phase-08-m3`)

| # | Note |
|---|---|
| A15 | `attendance/leave.py`: request (guardian for a child, student for themselves, staff for themselves, or a reviewer on their behalf), decide (approve or reject, with an optional note), cancel (pending, or approved leave that has not started). Overlapping pending or approved leave of the same person is refused; at most 60 days per request and 30 days in the past; half days are single dates |
| A16 | **Reviewers by permission combination, not role:** `attendance.leave.review` in the person's institution plus — for students — `attendance.record.manage` at the institution or the student's campus, or being the class teacher of the student's current unit; for staff — `staff.profile.view` at the institution or the staff member's campus. So a class teacher reviews only their own units' students (the M1 refinement, plan §18.1 A8), HR reviews staff leave, and a coordinator reviews students' |
| A17 | **Workflow:** new institution setting `attendance.leave_workflow` (a workflow key, default none) and the workflow subject `attendance.leave_request`. With a published workflow, it starts with the request (its start permission should be `attendance.leave.request`) and must finish before the decision, as for admission applications; without one, the decision is the built-in single step |
| A18 | Approved leave is pre-filled in registers through the roster (M2) and never overwrites a saved status; the requester gets an in-app notification of the decision. Audit events `attendance.leave.requested/decided/cancelled` (kind, days, decision only; reasons and notes never logged). Migration `0003` adds `decision_note` |
| A19 | API: `attendance/leave/` (list visible requests, request), `…/{id}/`, `…/{id}/decide/`, `…/{id}/cancel/`; hidden requests answer 404 |
| A20 | **Deviation: attachments are not built in M3.** Guardians hold no file-upload permission and the generic upload API is staff-facing; a guardian-facing upload for leave evidence needs its own authorisation. Recorded as a known gap, to be revisited with the frontend (M8) |

### 18.4 M4 — staff daily register (2026-11-28, branch `feat/phase-08-m4`)

| # | Note |
|---|---|
| A21 | `attendance/staff_register.py`: the day's register of active staff in the member's scope (`attendance.staff.mark` or `…view` at the institution: everyone; at a campus: the staff whose home campus it is), with saved status, approved staff leave (pre-filled, never overwriting) or the default; save in one request (status, check-in, check-out after check-in, remark); one record per staff member and date, concurrent first saves resolved by the unique constraint |
| A22 | **Deviation from plan §4 for staff:** past the edit window the staff register needs a reason and a fresh step-up, but not `attendance.record.manage` (HR holds `attendance.staff.mark`, MFA, and not the student-register code). Future dates are refused |
| A23 | `staff/mine/`: one's own days for a month (`staff.profile.view_own`, the profile linked to one's login). Audit event `attendance.staff.saved` (ids, statuses, counts, whether a reason was given) |
| A24 | API: `attendance/staff/register/` (GET, institution and date, optional campus), `…/register/save/`, `attendance/staff/mine/`. A query-parameter institution id is parsed as a UUID before the scope check (a plain string did not match the permission engine's targets and answered 404; found by the API test) |

### 18.5 M5 — absence alerts, flags and the nightly job (2026-11-28, branch `feat/phase-08-m5`)

| # | Note |
|---|---|
| A25 | **Absence alerts:** `ATTENDANCE_SUBMITTED_HANDLERS` queues `attendance.send_absence_alerts` (tenant task, module-gated) after a submission commits. Guardians who receive notices and have a portal login get an in-app notification (email when `attendance.alert_email` is on); `attendance.alert_guardians` off sends nothing. **Once per student per day** is enforced by the new table `attendance_absencealert` (unique student and date; also records how many logins were told) |
| A26 | **Figures** (`attendance/stats.py`): days from records of registers taken; a day is attended (present or late), absent, or not counted (excused, leave); percentage = attended ÷ (attended + absent), `None` with nothing counted; trailing consecutive absences. The `academics.promotion` namespace gains `attendance.*` variables through the new `STUDENTS_PROMOTION_CONTEXT` hook (students never imports attendance) |
| A27 | **P29** `attendance.nightly` (system, per-tenant iteration, daily beat) → `attendance.nightly_tenant`: `lock_due`, then flags for open years: below `attendance.threshold_percent`, or a published `attendance.flag` rule (variables `attendance.*`, `today`) is true. New table `attendance_studentflag` (unique student and year): class teachers (advisors with logins) are notified once when a flag appears; a cleared flag is removed so a relapse notifies again |
| A28 | Migrations `0004` (the two tables) and `0005` (composite keys, standard RLS, reversal refused). Platform catalogue now P1–P29. New selectors: `students.notice_memberships`, `students.active_enrollments`, `students.current_year_id`, `staff.advisor_memberships` |
| A29 | **Not in M5:** a correction from absent to present sends no follow-up (plan §7); SMS waits for Phase 14 (ADR-081 Q5). Flags are computed over the year to date; a per-term window can come with reports (M6) |

### 18.6 M6 — reports, CSV, the monthly register and the portal (2026-11-28, branch `feat/phase-08-m6`)

| # | Note |
|---|---|
| A30 | `attendance/reports.py`: daily register status per unit (taken or missing, state, marked, absent), a unit's students x days month with percentages, per-student figures over a range (at most a year), and the staff month. **Access by permission combination:** student reports need `attendance.report.view` plus `attendance.record.view` or `…manage`; the staff report needs `attendance.report.view` plus `attendance.staff.view` or `…mark`; held only at a campus, they cover that campus. So HR sees the staff report but not students' attendance |
| A31 | CSV for every report (`?export=csv`), formula-safe: `safe_cell` moved from the Phase 7 import to `apps/core/spreadsheets.py` (with `csv_text`), used by both (no duplicated code). Template kind `attendance.monthly_register` (sandboxed, ADR-056) renders the printable register; server PDF stays in Phase 9 |
| A32 | **Deviation (module boundary):** the portal view lives in `attendance` as `attendance/portal/students/{id}/` rather than under `/portal/children/`, because `parent_portal` does not depend on `attendance`. It shows only one's children or oneself (`students.child.view` / `…profile.view_own`, checked through `students.selectors.relation_to`): the month's days, year-to-date figures, whether flagged, and leave requests |
| A33 | New read selectors in `students`: `active_units`, `active_enrollments_in`. API answers 404 when the caller lacks the report scope for an institution or unit (the permission class answers 403 without any report code) |

### 18.7 M7 — partition evaluation and the device API design (2026-11-28, branch `feat/phase-08-m7`)

| # | Note |
|---|---|
| A34 | **Partition evaluation (exit criterion):** `infra/scripts/attendance_partition_eval.sql` builds 5 M generated rows twice (plain and monthly-partitioned) in a throwaway database with the production indexes and RLS, and times the report queries as a non-owner `NOBYPASSRLS` role. Every query took under 40 ms and partitioning brought no gain. Measurements, conclusion and migration path are in ADR-080. The scratch database and role were dropped afterwards; no real data was touched |
| A35 | **Device API design:** `docs/ATTENDANCE_DEVICE_API.md`: device registration with hashed secrets and IP allow-lists, an idempotent batch event endpoint keyed by device event id, clock-skew and rate limits, person references without biometric data, and derivation of the staff register that never overwrites a person's save. Nothing is built (ADR-079); it waits for ADR-028 and a real device |
| A36 | These are local measurements on a 4-CPU container, not production numbers; the Phase 18 benchmark re-measures them together with D9 |

### 18.8 M8 — frontend (2026-11-28, branch `feat/phase-08-m8`)

| # | Note |
|---|---|
| A37 | `/attendance` (en and bn, mobile-first) with tabs shown by permission: **Today** (the teacher's due registers for a date, open or take), **Registers** (an institution's registers on a date), **Leave** (visible requests, decide with a note, cancel), **Staff register** (status, check-in and check-out per staff member, reason past the window), **Reports** (daily status and the student summary, each with a CSV link). A navigation entry appears with any attendance code and the module |
| A38 | **Quick-mark screen:** one large button per student (at least 48 px tall) that cycles present → absent → late, plus a menu for excused and leave; live counts; a sticky Save / Submit bar on phones. Save sends only changed rows and rows never saved, with the register version. A 409 (`stale_register`, now a known error code in en and bn) shows a reload prompt instead of overwriting. Past the edit window a reason is required (the server also asks for step-up, handled by the existing step-up recovery). Locked registers offer an unlock dialog to managers |
| A39 | The portal shows each child's (or one's own) attendance month, the year's percentage, the low-attendance flag, leave requests and a leave form, only when the organisation has the `attendance` module |
| A40 | Server data is never copied into effects: the register sheet is remounted with a new key when the server returns a new version, and the staff register keeps only the marker's edits over the server rows (ESLint `react-hooks/set-state-in-effect`). Pure helpers (`nextStatus`, `changedEntries`, counts, local dates) have unit tests |
| A41 | **Still deferred:** leave attachments (plan §18.3 A20) remain a known gap; the M9 E2E will exercise these screens on a mobile viewport |

### Change notes
- 2026-11-28 — Created (Proposed) after the owner approved Phase 7.
- 2026-11-28 — Approved by the owner with all recommended answers (ADR-081); ADR-076 to ADR-080 Accepted.
- 2026-11-28 — §18.1 appended: M1 notes A1–A8.
- 2026-11-28 — §18.2 appended: M2 notes A9–A14.
- 2026-11-28 — §18.3 appended: M3 notes A15–A20.
- 2026-11-28 — §18.4 appended: M4 notes A21–A24.
- 2026-11-28 — §18.5 appended: M5 notes A25–A29.
- 2026-11-28 — §18.6 appended: M6 notes A30–A33.
- 2026-11-28 — §18.7 appended: M7 notes A34–A36.
- 2026-11-28 — §18.8 appended: M8 notes A37–A41.
