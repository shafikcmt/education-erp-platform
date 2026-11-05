# Project Vision

> Authoritative summary lives in `CLAUDE.md` §1. This document expands it.

## 1. Vision statement

Give every education institution — regardless of type, size or country — a premium, reliable, affordable operating system for running the institution, delivered as one configurable multi-tenant SaaS.

## 2. Problem

Institutions typically suffer from one or more of:

- Paper registers and spreadsheets for admissions, attendance, marks and fees → errors, lost data, slow reporting.
- Generic ERPs built for one institution type (usually schools) that do not fit universities (credit systems, CGPA), madrasas (Marhala/Kitab structures, Hifz tracking, residential life) or coaching centers (batches, model tests).
- Custom software built separately for each institution → expensive, unmaintained, insecure, no upgrades.
- Poor mobile experience for parents and students.
- Weak financial controls (cash leakage, no audit trail, untraceable waivers).

## 3. Solution principles

1. **Configure, don't fork.** One codebase; institution-type presets and tenant-level declarative customization.
2. **Modular and sellable.** Modules can be enabled per plan/add-on; tenants pay for what they use.
3. **Correct by construction.** Tenant isolation, permission checks and financial integrity are enforced in the platform core, not left to each feature.
4. **Mobile-first, premium UX.**
5. **Global from day one,** with strong local fit (language, currency, payment gateways, grading conventions).

## 4. Target segments

| Segment | Key needs | Notes |
|---|---|---|
| Schools | Admissions, attendance, exams/report cards, fees, parent communication | Largest volume segment |
| Colleges | Groups/streams, board exam preparation, fees, results | |
| Universities | Faculties/departments/programs, credit-based registration, semesters, CGPA/transcripts, halls of residence | Higher ACV, longer sales cycle, often enterprise |
| Madrasas | Marhala/Jamaat/Kitab structures, Hifz progress, residential hostel, guardian communication, Arabic/Bengali/Urdu text | Often under-served by generic ERPs |
| Coaching centers | Batches, short programs, model tests, fee installments, SMS results | Price-sensitive, fast decisions |
| Training institutes | Courses/cohorts, trainers, certificates, short-cycle enrollment | |

## 5. Personas

- **Tenant owner / chairman** — wants financial visibility, growth, control.
- **Principal / institution admin** — wants smooth daily operations and reports.
- **Accountant / cashier** — wants fast, error-free fee collection and reconciliation.
- **Teacher** — wants quick attendance and marks entry on a phone.
- **Student** — wants schedules, results, assignments, online tests.
- **Parent / guardian** — wants attendance alerts, results, fee dues and easy online payment.
- **Hostel warden** — wants allocations, roll-calls, leave approvals.
- **Super Admin (platform)** — wants tenant lifecycle, billing and health visibility.

## 6. Business model

- Subscription plans (`trial`, `starter`, `growth`, `professional`, `enterprise`).
- Paid add-on modules and usage-based extras (SMS, storage, AI).
- Enterprise contracts (custom extensions, SSO, dedicated infra, SLA).
- Onboarding/data-migration and training services (optional revenue).

Price levels are **not decided**; see `SUBSCRIPTION_AND_BILLING.md` and ADR-024.

## 7. Success metrics (proposed — to be confirmed by owner)

| Metric | Purpose |
|---|---|
| Time-to-first-value (tenant signup → first attendance/fee recorded) | Onboarding quality |
| Monthly active users by role (teachers, parents) | Real adoption |
| Online fee-payment share | Value to institutions |
| Net revenue retention, logo churn | SaaS health |
| P95 API latency, uptime | Reliability |
| Cross-tenant incidents (target: zero) | Trust |

These are measurement categories, not committed numeric targets; numeric targets require owner approval.

## 8. Non-goals (for now)

- Separate per-institution codebases or white-label forks.
- Native mobile apps before the web app is stable (a PWA-quality mobile web experience comes first; native apps are a future decision).
- Arbitrary tenant-uploaded executable code.
- Microservices before measured need.

### Change notes
- 2026-11-05 — Initial version (Phase 0).
