# Requirements

> Requirement IDs are stable; reference them in PRs and tests. Priority: **M** = must (MVP), **S** = should, **C** = could (later).
> Phase = roadmap phase that delivers it (see `DEVELOPMENT_ROADMAP.md`).

## 1. Platform & Tenancy

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| PLT-01 | Single codebase serves all tenants and institution types | M | 1+ |
| PLT-02 | Hierarchy `Tenant → Institution → Campus`; a tenant can own multiple institutions of different types | M | 3 |
| PLT-03 | Tenant resolution by subdomain and verified custom domain | M (subdomain), S (custom domain) | 3 / 18 |
| PLT-04 | Strict server-side tenant isolation on all data, files, caches, tasks, search and embeddings | M | 3+ |
| PLT-05 | Tenant settings: locales, timezone, currency, branding, academic calendar defaults, number formats | M | 3, 5 |
| PLT-06 | Self-service tenant signup with trial plan and institution-type preset | S | 3–5 |
| PLT-07 | Super Admin console: tenant lifecycle (create, suspend, reactivate, offboard), plan changes, health | M | 3–4 |
| PLT-08 | Tenant data export (portable format) and verified deletion on offboarding | S | 18 |
| PLT-09 | Audited, time-bound support access to tenant data | M | 3 |
| PLT-10 | Usage limits per plan enforced server-side | M | 4 |

## 2. Identity, Roles, Permissions

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| IAM-01 | Email + password login; one user account may belong to multiple tenants/institutions with different roles (memberships built in Phase 3). Phone/SMS login moved to Phase 14 (ADR-037) | M | 2 (email), 3 (memberships), 14 (phone) |
| IAM-02 | Password reset, activation, email verification (no public registration, ADR-037); tenant invitations | M | 2 (reset/activation/verification), 3 (invitations) |
| IAM-03 | MFA (TOTP + recovery codes), mandatory for privileged accounts (ADR-035); step-up for sensitive operations | M | 2 |
| IAM-04 | Permission codes `<module>.<resource>.<action>`; roles = permission bundles | M | 2 |
| IAM-05 | Role assignments scoped to tenant / institution / campus (and own-records for students/guardians/teachers) | M | 2–3 |
| IAM-06 | System role templates per institution type; tenants can clone/customize roles | M | 2, 5 |
| IAM-07 | Session management: list/revoke sessions; 30 min idle and 12 h absolute timeouts; sign-in history via audit; new sign-in notices | M | 2 |
| IAM-08 | Enterprise SSO (SAML/OIDC) | C | 17/18 |
| IAM-09 | Brute-force protection and rate limiting on auth endpoints; no user enumeration | M | 2 |
| IAM-10 | Platform staff have no implicit tenant-data access; audited, time-limited support sessions | M | 2 (enforced), 3 (support sessions) |
| IAM-11 | Security-event IPs encrypted, access-restricted, retained per policy and anonymized (ADR-036) | M | 2 |

## 3. Module Registry & Entitlements

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| MOD-01 | Module manifests: code, version, dependencies, permissions, settings schema, menu entries | M | 4 |
| MOD-02 | Entitlement resolution: plan modules + add-ons + overrides → enabled modules per tenant | M | 4 |
| MOD-03 | Server rejects API calls to non-entitled modules (HTTP 403 with `module_not_entitled`) | M | 4 |
| MOD-04 | Feature flags (platform-wide, per plan, per tenant) for gradual rollout | M | 4 |
| MOD-05 | Frontend receives entitlement + permission manifest to render navigation | M | 4 |

## 4. Customization

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| CUS-01 | Institution-type presets (L2) applied on institution creation, versioned | M | 5 |
| CUS-02 | Terminology overrides per tenant/institution, multi-language | M | 5 |
| CUS-03 | Custom fields on supported entities with validation, permissions, visibility | M | 5 |
| CUS-04 | Form builder (admission, inquiry, etc.) using core + custom fields | S | 5–6 |
| CUS-05 | Declarative workflows/approvals (state machine) | S | 5 |
| CUS-06 | Declarative rules (safe expressions) for fees, grading, promotion, attendance | S | 5, 9, 10 |
| CUS-07 | Document templates (report card, ID card, certificate, receipt, admit card) | M | 5, 9, 10 |
| CUS-08 | Numbering sequences (student ID, invoice, receipt) — gap-free where required | M | 5 |
| CUS-09 | Configuration versioning: draft, publish, rollback, history, audit | M | 5 |
| CUS-10 | Custom entities/screens (custom module builder) | C | 17 |

## 5. Academic & Admission

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| ACA-01 | Academic years/sessions, terms/semesters with configurable calendars | M | 6 |
| ACA-02 | Configurable structure levels (class/section; faculty/department/program; marhala/jamaat; batch) | M | 6 |
| ACA-03 | Subjects/courses/kitabs with credits (optional), teachers assignment | M | 6 |
| ACA-04 | Timetable (periods, rooms, teacher clash detection) | S | 6 |
| ACA-05 | Promotion/progression rules and bulk promotion | M | 6–9 |
| ADM-01 | Inquiry tracking and online application form (public, tenant-branded) | M | 6 |
| ADM-02 | Application review workflow, admission test scheduling, merit list | S | 6 |
| ADM-03 | Convert application → student enrollment with fee assignment | M | 6, 10 |

## 6. People

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| PPL-01 | Student profile, documents, guardians (N–N), enrollment history | M | 7 |
| PPL-02 | Staff/teacher profiles, departments, designations, subject assignments | M | 7 |
| PPL-03 | Guardian portal: children overview, attendance, results, fees, notices | M | 7 |
| PPL-04 | Student portal: timetable, results, assignments, fees | M | 7 |
| PPL-05 | Bulk import (CSV/XLSX) with validation report | M | 7 |
| PPL-06 | ID card generation from templates | S | 7 |
| PPL-07 | Transfer certificates, alumni status | S | 7 |

## 7. Attendance

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| ATT-01 | Daily and period/session-wise student attendance, mobile-friendly | M | 8 |
| ATT-02 | Staff attendance and leave | M | 8 |
| ATT-03 | Absence alerts to guardians | M | 8, 14 |
| ATT-04 | Device integration API (biometric/RFID/QR) | C | 8 |
| ATT-05 | Attendance thresholds and reports | M | 8, 15 |

## 8. Examinations

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| EXM-01 | Configurable grading schemes (marks, letter grades, GPA, CGPA, pass rules) | M | 9 |
| EXM-02 | Exam setup, components (written/MCQ/practical), weightage | M | 9 |
| EXM-03 | Marks entry with validation, locking and moderation workflow | M | 9 |
| EXM-04 | Result processing, publication, report cards, transcripts, merit position | M | 9 |
| EXM-05 | Admit cards, seat plans | S | 9 |

## 9. Fees & Accounting

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| FIN-01 | Fee heads, fee structures per class/program/batch, installments | M | 10 |
| FIN-02 | Invoices, discounts, scholarships, waivers (with approval workflow) | M | 10 |
| FIN-03 | Payments: cash, bank, online gateways; receipts; partial payments | M | 10 |
| FIN-04 | Late fines via rules | S | 10 |
| FIN-05 | Refunds and adjustments via reversal, never deletion | M | 10 |
| FIN-06 | Double-entry accounting: chart of accounts, journals, ledgers, trial balance, P&L, balance sheet | M | 10 |
| FIN-07 | All money operations atomic, idempotent and audited | M | 10 |
| FIN-08 | Day-close / cash reconciliation | S | 10 |
| FIN-09 | Multi-currency per tenant (single functional currency per institution) | S | 10 |

## 10. HR & Payroll

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| HRP-01 | Employee records, contracts, leave types and balances | M | 11 |
| HRP-02 | Salary structures, allowances/deductions, payroll runs, payslips | M | 11 |
| HRP-03 | Payroll posts to accounting | M | 11 |
| HRP-04 | Advances/loans, statutory deductions configurable per country | S | 11 |

## 11. Hostel, Transport, Library

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| HST-01 | Configurable Hostel Engine: hostels, blocks, floors, rooms, beds | M | 12 |
| HST-02 | Hostel profiles: madrasa residential, university hall, generic | M | 12 |
| HST-03 | Applications, allocation policies (manual/rule/merit/lottery), transfers, check-in/out | M | 12 |
| HST-04 | Roll-calls (configurable times), leave/out-pass with guardian authorization, visitor log | M | 12 |
| HST-05 | Mess/meal plans and hostel fees integrated with `fees` | S | 12 |
| TRN-01 | Vehicles, routes, stops, student assignment, transport fees | M | 12 |
| LIB-01 | Catalog, copies, circulation, reservations, fines | M | 12 |

## 12. LMS & Online Exams

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| LMS-01 | Course content (files, links, video links), assignments, submissions, grading | M | 13 |
| OEX-01 | Question bank (MCQ, short answer, etc.), tagging by subject/topic/difficulty | M | 13 |
| OEX-02 | Online tests with timers, randomization, auto-grading, result publishing | M | 13 |
| OEX-03 | Basic integrity controls (time windows, attempt limits, tab-switch logging) | S | 13 |

## 13. Communication

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| COM-01 | Notices/announcements targeted by institution/campus/class/role | M | 14 |
| COM-02 | SMS, email, push, in-app via provider abstraction; templates; delivery logs | M | 14 |
| COM-03 | SMS credit metering per tenant | M | 14 |
| COM-04 | Event-driven notifications (absence, result published, fee due, payment received) | M | 14 |

## 14. Reports & Analytics

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| RPT-01 | Standard reports per module, exports (CSV/XLSX/PDF) | M | 15 |
| RPT-02 | Role-based dashboards | M | 15 |
| RPT-03 | Custom report builder over permitted datasets | S | 15 |
| RPT-04 | Platform analytics for Super Admin (aggregated, no tenant PII) | S | 15 |

## 15. AI Assistant

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| AI-01 | Conversational assistant answering questions over data the user is permitted to see | M | 16 |
| AI-02 | Tool-based actions through service layer with full authorization pipeline | M | 16 |
| AI-03 | Tenant-scoped RAG over tenant documents (pgvector) | S | 16 |
| AI-04 | Per-tenant opt-in, quotas, audit, PII minimization | M | 16 |

## 16. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-01 Security | OWASP ASVS Level 2 target; see `SECURITY.md` |
| NFR-02 Isolation | Zero cross-tenant data exposure; automated isolation tests per module |
| NFR-03 Performance (proposed) | P95 API latency < 300 ms for standard CRUD at expected load; list endpoints paginated |
| NFR-04 Availability (proposed) | 99.9% monthly for production (excl. planned maintenance) |
| NFR-05 Backup (proposed) | RPO ≤ 15 min, RTO ≤ 4 h; restore tested at least quarterly |
| NFR-06 Scalability | Horizontal scaling of stateless `web`, `api`, `worker`; DB vertical + read replicas later |
| NFR-07 i18n | English + Bengali initial; Arabic RTL support; all strings translatable |
| NFR-08 Accessibility | WCAG 2.2 AA target |
| NFR-09 Mobile-first | All core teacher/parent/student flows usable on 360 px wide screens |
| NFR-10 Observability | Structured logs, Sentry, health checks, metrics, alerting |
| NFR-11 Auditability | All security-relevant and financial actions audited, append-only |
| NFR-12 Privacy | Data minimization, retention policies, consent for AI processing, export/deletion |
| NFR-13 Maintainability | Modular boundaries, tests, typed code, docs updated per change |

Numeric NFR targets marked *proposed* require owner approval (see `DECISION_LOG.md`).

### Change notes
- 2026-11-05 — Initial version (Phase 0).
- 2026-11-05 — Aligned with Phase 2 approvals (ADR-031 to ADR-037); see `plans/PHASE_02_PLAN.md` rev. 2.
