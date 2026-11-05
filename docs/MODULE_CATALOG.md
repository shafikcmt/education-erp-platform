# Module Catalog

> Canonical module codes (see `CLAUDE.md` §5). Each module ships a `manifest.py` declaring: `code`, `version`, `category`, `dependencies`, `permissions`, `settings_schema`, `menu`, `events_emitted`, `events_consumed`.
> **Availability** column shows the *proposed* default packaging; final packaging is decided in `SUBSCRIPTION_AND_BILLING.md` (ADR-024).

## 1. Summary

| Code | Category | Depends on | Phase | Proposed availability |
|---|---|---|---|---|
| `core` | platform | — | 1 | Always |
| `identity` | platform | core | 2 | Always |
| `rbac` | platform | identity | 2 | Always |
| `tenancy` | platform | identity, rbac | 3 | Always |
| `audit` | platform | core | 2–3 | Always |
| `files` | platform | tenancy | 3 | Always (quota by plan) |
| `module_registry` | platform | tenancy | 4 | Always |
| `billing` | platform | module_registry | 4 | Always |
| `customization` | platform | module_registry | 5 | Always (advanced features by plan) |
| `notifications_core` | platform | tenancy | 5/14 | Always |
| `academics` | standard | customization | 6 | All plans |
| `timetable` | standard | academics, staff | 6/7 | growth+ |
| `admissions` | standard | academics, customization | 6 | All plans (online forms growth+) |
| `students` | standard | academics | 7 | All plans |
| `staff` | standard | academics | 7 | All plans |
| `parent_portal` | standard | students | 7 | All plans |
| `attendance` | standard | students, staff | 8 | All plans |
| `examinations` | standard | academics, students | 9 | All plans |
| `fees` | standard | students, accounting posting engine (always installed, ADR-025) | 10 | All plans |
| `accounting` | standard | tenancy | 10 | Posting engine always; GL features growth+ or add-on (ADR-025) |
| `hr_payroll` | standard | staff, accounting | 11 | add-on / professional+ |
| `hostel` | standard | students, fees, attendance | 12 | add-on |
| `transport` | standard | students, fees | 12 | add-on |
| `library` | standard | students, staff | 12 | add-on / professional+ |
| `lms` | standard | academics, students, staff | 13 | add-on |
| `online_exams` | standard | academics, students | 13 | add-on |
| `communication` | standard | notifications_core | 14 | All plans (SMS credits metered) |
| `reports_analytics` | standard | all entitled modules | 15 | Basic all; advanced professional+ |
| `ai_assistant` | standard | module_registry, rbac, all entitled modules | 16 | add-on |
| `custom_module_builder` | extension | customization | 17 | enterprise |
| `ext_hifz_tracking` | extension (madrasa) | students, academics | 17 | madrasa add-on |
| `ext_course_registration` | extension (university) | academics, students, fees | 17 | university add-on |
| `ext_batch_management` | extension (coaching) | academics, fees | 17 | coaching (bundled in preset) |
| `ext_certification` | extension (training) | academics, examinations | 17 | training add-on |

## 2. Platform modules

### core
Base models, tenant context primitives, request ID, structured logging helpers, error format, pagination, common validators, money utilities, domain event bus, health endpoints.

### identity
User accounts, login (email/phone + password), password reset, invitations, verification, MFA (TOTP), sessions, login history, brute-force protection. Permissions: `identity.user.*`, `identity.session.revoke`.

### rbac
Permission registry (seeded from manifests), roles (system templates + tenant roles), scoped role assignments, permission evaluation API (`has_perm(actor, code, scope)`), role templates per institution type. Permissions: `rbac.role.view|create|update|delete|assign`.

### tenancy
Tenants, domains, institutions, campuses, tenant settings, lifecycle, onboarding wizard backend, support sessions. Permissions: `tenancy.institution.*`, `tenancy.campus.*`, `tenancy.settings.update`.

### audit
Append-only audit events, data-access log for sensitive records, support-session logging, audit viewer API. Permissions: `audit.event.view`.

### files
Upload/download via presigned URLs, tenant-prefixed keys, MIME/size validation, malware-scan hook, quotas, retention classes.

### module_registry
Module manifests, versions, dependency validation, tenant entitlement resolution and caching, feature flags, navigation/permission manifest for frontend.

### billing
Plans, prices, add-ons, subscriptions, trials, usage metering, limit enforcement, SaaS invoices and payments, dunning, gateway abstraction. Super Admin only for management; tenant owners see their subscription. Permissions: `billing.subscription.view|manage`.

### customization
Presets, configuration sets, terminology, custom fields, forms, workflows, rules, templates, numbering sequences, versioning/publishing. See `CUSTOMIZATION_ENGINE.md`. Permissions: `customization.<artefact>.view|edit|publish`.

### notifications_core
Channel-agnostic dispatch, user notification preferences, quiet hours, provider abstraction (used by `communication`).

## 3. Standard ERP modules

### academics
Academic years/sessions, terms/semesters, configurable structure levels and academic unit tree (class/section, faculty/department/program, marhala/jamaat, batch), subjects/courses/kitabs with optional credits, offerings, teacher assignment, promotion rules. Capability flags: `academics.credit_based`, `academics.semester_based`, `academics.section_enabled`.

### timetable
Periods/bell schedules, rooms, timetable slots, teacher/room clash detection, substitutions, student/teacher timetable views.

### admissions
Inquiries/leads, admission cycles, public application forms (Studio forms), document uploads, application fee, review workflow, admission test & interview scheduling, merit lists, offer/acceptance, conversion to student + enrollment + fee assignment.

### students
Student profiles, custom fields, guardians (N–N), documents, enrollment history, bulk import, promotion/transfer, transfer certificate, ID cards, alumni status, discipline notes (permission-restricted).

### staff
Teacher/staff profiles, departments, designations, qualifications, teaching assignments, staff documents (HR-sensitive fields masked by permission).

### parent_portal
Guardian and student self-service: children switcher, attendance, results, fees & online payment, notices, timetable, assignments, leave requests.

### attendance
Daily / period / session attendance, quick mobile marking, late/excused, leave requests (workflow), staff attendance, thresholds & alerts, device integration API (biometric/RFID/QR, later), hostel roll-call kind (used by `hostel`).

### examinations
Grading schemes (marks, letters, GPA/CGPA, divisions), exam definitions, components & weightage, marks entry with locking/moderation, result processing (reproducible from inputs), publishing, report cards/transcripts via templates, merit positions, admit cards, seat plans.

### fees
Fee heads, structures & installments, student fee assignment, invoices, concessions (discount/scholarship/waiver with approvals), payments (cash/bank/online), allocation, receipts, late fines (rules), refunds (reversals), dues & reminders, day-close. All money rules in `DATABASE_DESIGN.md` §2.8.

### accounting
Chart of accounts (preset per institution type/country), double-entry journal, vouchers (receipt/payment/journal/contra), ledgers, fiscal periods & closing, bank accounts & reconciliation, trial balance, income statement, balance sheet, cash flow. Fee and payroll postings are automatic.

### hr_payroll
Employee contracts, leave types/balances, attendance link, salary structures (components, formulas via safe rules), payroll runs (draft → review → approved → paid), payslips, advances/loans, statutory deductions configurable per country, bank payment files (later), accounting postings.

### hostel — Custom Hostel Engine {#hostel}
Configurable engine for madrasa residential life and university halls (and generic hostels):
- **Structure:** hostel → block → floor → room → bed; room types, capacity, facilities, gender/eligibility.
- **Profiles (L2 presets):** `hostel.madrasa_residential`, `hostel.university_hall`, `hostel.generic`. Profiles set defaults for allocation policy, tenure, roll-call schedule, leave/out-pass workflow, visitor rules, meal plans, staff roles, fee plans.
- **Applications & allocation:** manual, rule-based (eligibility rules), merit-ranked, or lottery; waitlists; room change requests; check-in/check-out with inventory checklist.
- **Residential operations:** multiple daily roll-calls, curfew tracking, out-pass/leave with guardian authorization (SMS/app confirmation), visitor log with approved-visitor list, incidents/discipline log, warden duty roster.
- **Mess/meals:** meal plans, subscriptions, meal attendance/counts, mess bills.
- **Finance:** hostel fees and mess bills generated through `fees` (never separate money handling).
- **Roles/permissions:** `hostel.*` permissions; role templates `hostel_warden` (madrasa label e.g. *Nazim/Superintendent*, university label e.g. *Provost/House Tutor* via terminology).

### transport
Vehicles, drivers, routes, stops, schedules, student/staff assignments, transport fees via `fees`, pickup/drop logs; GPS integration later (not in scope until approved).

### library
Catalog (books/kitabs, multilingual titles), copies/barcodes, members, issue/return/renew, reservations, fines via `fees`, inventory reports.

### lms
Course spaces per offering, content (files, links, embedded video links), assignments, submissions, rubric/marks, announcements, online class links (external meeting tools).

### online_exams
Question bank (MCQ single/multi, true/false, short answer, numeric; tags by subject/topic/difficulty), test assembly (fixed/random), schedules & windows, timers, attempt limits, auto-grading, manual grading for subjective items, result publishing (optionally into `examinations`), integrity logs (tab-switch, IP).

### communication
Notices/announcements targeting (institution/campus/unit/role/individuals), SMS/email/push/in-app, templates (Studio), scheduled sends, delivery logs, SMS credit metering, guardian messaging rules.

### reports_analytics
Standard report library per module, exports (CSV/XLSX/PDF, async for large), role dashboards, custom report builder over **permitted datasets only**, scheduled reports, platform aggregate analytics (no tenant PII).

### ai_assistant
See `AI_ASSISTANT.md`.

## 4. Extensions (Phase 17)

| Code | Purpose |
|---|---|
| `custom_module_builder` | Tenant-defined entities (backed by JSONB + definitions), list/detail/form screens, permissions, workflows — declarative only |
| `ext_hifz_tracking` | Quran memorization progress (para/surah/ayah ranges, revision cycles — *sabaq/sabqi/manzil* style configurable), teacher evaluation, guardian reports |
| `ext_course_registration` | Credit-based course registration windows, prerequisites, credit limits, add/drop, section capacity, registration fees |
| `ext_batch_management` | Coaching batches, rolling admissions, batch transfer, installment-heavy fees, model test series linkage |
| `ext_certification` | Course completion criteria, certificate issuance with verification code/QR, public verification page |

## 5. Permission naming examples

```
students.student.view          students.student.create      students.student.update
students.student.export        students.guardian.view       students.document.view_sensitive
attendance.record.mark         attendance.record.edit_past  attendance.report.view
examinations.mark.enter        examinations.mark.lock       examinations.result.publish
fees.invoice.create            fees.payment.collect         fees.payment.refund
fees.concession.approve        accounting.journal.post      accounting.period.close
hostel.allocation.manage       hostel.outpass.approve       hostel.rollcall.mark
customization.field.edit       customization.config.publish ai_assistant.chat.use
```

### Change notes
- 2026-11-05 — Initial version (Phase 0).
