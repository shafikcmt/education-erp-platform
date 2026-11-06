# Database Design

> PostgreSQL 17 is the only primary datastore (ADR-004). Diagrams: `ERD.md`. Tenancy: `MULTI_TENANT_ARCHITECTURE.md`.
> This is the **target design**. Tables are created phase by phase; field lists are indicative and finalized in each phase's plan.

## 1. Conventions

| Topic | Convention |
|---|---|
| Naming | `snake_case`; table names `<app>_<model>` (Django default) |
| Primary keys | UUIDv7 (ADR-012, accepted), native `uuid` type, generated only by `core.ids.new_id()` |
| Tenant column | `tenant_id UUID NOT NULL` + index on every tenant-owned table; usually leading column of composite indexes |
| Timestamps | `created_at`, `updated_at` (`timestamptz`, UTC) |
| Actors | `created_by_id`, `updated_by_id` (nullable FK to user) |
| Soft archive | Master data: `is_active` / `archived_at`; **no hard delete** of records referenced by finance, exams or audit |
| Financial records | Immutable after posting; corrections by reversal entries; no `UPDATE` of amounts |
| Money | `NUMERIC(18,2)` + `currency CHAR(3)`; never float |
| Percentages/rates | `NUMERIC(7,4)` |
| Dates | Academic/business dates `date`; events `timestamptz`; display in tenant/campus timezone |
| Enums | Text choices (Django `TextChoices`) + `CHECK` constraint; avoid PostgreSQL enum types (painful migrations) |
| Custom data | `extra JSONB NOT NULL DEFAULT '{}'` validated against `customization.CustomFieldDefinition`; GIN index only where filtered |
| Translations | Translatable master names stored as `name` + `name_i18n JSONB` (`{"bn": "...", "ar": "..."}`) |
| Optimistic locking | `version INTEGER` on records edited concurrently (marks, timetable, config drafts) |
| Uniqueness | Business keys unique per tenant: `UNIQUE (tenant_id, code)` |
| Large append-only tables | Range-partitioned by month when volume requires (audit, attendance, notifications) |

### Base abstract models (Phase 1/3)

```python
class BaseModel(models.Model):        # id = UUIDField(primary_key=True, default=core.ids.new_id, editable=False), created_at, updated_at
class TenantScopedModel(BaseModel):   # tenant FK, TenantManager (fail closed), created_by, updated_by
class InstitutionScopedModel(TenantScopedModel):  # + institution FK
class CampusScopedModel(InstitutionScopedModel):  # + campus FK (nullable where "all campuses" is valid)
```

## 2. Schema by domain

### 2.1 Platform: tenancy

| Table | Key columns |
|---|---|
| `tenancy_tenant` | id, slug (unique), name, status, default_locale, timezone, currency, country, data_region, settings JSONB, branding JSONB |
| `tenancy_tenantdomain` | id, tenant_id, domain (unique), is_primary, verified_at, verification_token |
| `tenancy_institution` | id, tenant_id, institution_type, name, name_i18n, code, preset_code, preset_version, settings JSONB |
| `tenancy_campus` | id, tenant_id, institution_id, name, code, address JSONB, timezone (nullable override), is_main |
| `tenancy_supportsession` | id, tenant_id, staff_user_id, reason, ticket_ref, approved_by_id, starts_at, ends_at, revoked_at |

### 2.2 Identity & RBAC

| Table | Key columns |
|---|---|
| `identity_user` | id (UUIDv7), email (unique + case-insensitive unique index), password (Argon2, Django), is_active, is_staff, email_verified_at, activated_at, last_password_change_at, deactivated_at, locale, display_name, last_login (phone: Phase 14) |
| `tenancy_membership` (Phase 3, RLS) | id, tenant_id, user_id, status (invited/active/suspended/left), invited_by, joined_at, last_seen_at — `UNIQUE (tenant_id, user_id)` (ADR-032) |
| `identity_mfadevice`, `identity_recoverycode`, `identity_accounttoken`, `identity_sessionrecord`, `identity_seendevice` | Phase 2: encrypted TOTP secret (ADR-031); hashed recovery codes; hashed single-use tokens (ADR-034); per-user session index with encrypted IP (ADR-036); new sign-in detection. Login history = audit events |
| `rbac_permission` | code (`module.resource.action`, PK or unique), module_code, description — seeded from manifests |
| `rbac_role` | id, tenant_id (NULL = platform role/system template; dual-scope RLS in Phase 3), code, name, name_i18n, kind (platform/template/tenant), institution_types[], is_system |
| `rbac_rolepermission` | role_id, permission_code |
| `rbac_roleassignment` | id, tenant_id, membership_id, role_id, scope_type (tenant/institution/campus), institution_id, campus_id, valid_from, valid_until |
| `rbac_platformroleassignment` | user_id, role_id (kind = platform), granted_by, granted_at, reason |

Object-level scopes (e.g. teacher → own sections; guardian → own children) are computed by selectors from domain relations, not stored as role assignments.

### 2.3 Module registry & billing

| Table | Key columns |
|---|---|
| `module_registry_module` | code (unique), name, category (platform/standard/extension), current_version, is_sellable, dependencies JSONB |
| `module_registry_featureflag` | key, default_enabled, rules JSONB |
| `module_registry_tenantmodule` | tenant_id, module_code, source (plan/addon/override/trial), enabled, valid_from, valid_until, settings JSONB |
| `billing_plan` | code, name, is_public, limits JSONB (incl. `max_institutions`, `max_campuses`, `max_active_students`, …; ADR-010), included_modules (M2M via `billing_planmodule`) |
| `billing_price` | plan_or_addon, currency, interval (month/year), amount NUMERIC, metric (flat/per_student_tier), tiers JSONB, active_from/to |
| `billing_addon` | code, module_code, name |
| `billing_subscription` | tenant_id, plan_code, status, current_period_start/end, trial_ends_at, gateway, gateway_ref |
| `billing_subscriptionitem` | subscription_id, addon_code, quantity |
| `billing_usagerecord` | tenant_id, metric (active_students/sms/storage_gb/ai_tokens), period, quantity |
| `billing_saasinvoice`, `billing_saaspayment` | Platform ↔ tenant invoices and payments (immutable) |

### 2.4 Customization

| Table | Key columns |
|---|---|
| `customization_configset` | tenant_id (nullable for presets), scope_type, scope_id, namespace, status (draft/published/archived), version, data JSONB, published_by, published_at |
| `customization_preset` | code (e.g. `madrasa.qawmi.v1`), institution_type, version, data JSONB (platform-managed) |
| `customization_customfielddefinition` | tenant_id, entity_type, key, label_i18n, field_type, validation JSONB (JSON Schema), required, visibility, permission_code, order, version, is_active |
| `customization_formdefinition` | tenant_id, code, entity_type, layout JSONB, version, status |
| `customization_workflowdefinition` | tenant_id, code, entity_type, states JSONB, transitions JSONB, version, status |
| `customization_workflowinstance` | tenant_id, definition_id, definition_version, entity_type, entity_id, state, history JSONB |
| `customization_rule` | tenant_id, code, namespace, expression JSONB (ADR-016), version, status |
| `customization_template` | tenant_id, code, kind (report_card/id_card/certificate/receipt/sms/email), engine, body, version, status |
| `customization_numbersequence` | tenant_id, scope, code, pattern (e.g. `{INST}-{YYYY}-{SEQ:5}`), next_value, gap_free |
| `customization_terminology` | tenant_id, scope, locale, key, value |

### 2.5 Academics & admissions

| Table | Key columns |
|---|---|
| `academics_academicyear` | tenant_id, institution_id, name, start_date, end_date, is_current |
| `academics_term` | academic_year_id, name, kind (term/semester/trimester), start/end |
| `academics_structurelevel` | institution_id, level_index, code (e.g. faculty/department/program/class/section/marhala/jamaat/batch), label_i18n — defines the configurable hierarchy |
| `academics_unit` | tenant_id, institution_id, campus_id, level_id, parent_id (self FK), name, code, capacity — generic tree node (class, section, department, program, batch…) |
| `academics_subject` | tenant_id, institution_id, code, name, credit NUMERIC (nullable), subject_type |
| `academics_curriculum` / `academics_offering` | which subjects/courses are offered for a unit in a year/term, teacher assignments |
| `timetable_period`, `timetable_room`, `timetable_slot` | timetable data |
| `admissions_inquiry` | tenant_id, institution_id, contact info, source, status |
| `admissions_admissioncycle` | institution_id, academic_year_id, target unit(s), open/close dates, form_definition_id, fee |
| `admissions_application` | tenant_id, cycle_id, applicant data, extra JSONB, status, workflow_instance_id, score, merit_rank |

> The generic `academics_unit` tree with configurable `structurelevel`s is how one schema supports School (Class→Section), University (Faculty→Department→Program) and Madrasa (Marhala→Jamaat). Decision to confirm in Phase 6 plan.

### 2.6 People

| Table | Key columns |
|---|---|
| `students_student` | tenant_id, institution_id, student_code (unique per tenant), user_id (nullable), names (incl. i18n), dob, gender, extra JSONB, status |
| `students_guardian` | tenant_id, user_id (nullable), name, phone, email, relation defaults |
| `students_studentguardian` | student_id, guardian_id, relation, is_primary, can_pickup, receives_notifications |
| `students_enrollment` | tenant_id, student_id, academic_year_id, unit_id (class/section/program), roll_no, status, start/end |
| `students_document` | student_id, file_id, doc_type |
| `staff_staff` | tenant_id, user_id, employee_code, designation, department_unit_id, employment_type, extra JSONB |
| `staff_teachingassignment` | staff_id, offering_id / unit_id, role (subject teacher/class teacher) |

### 2.7 Attendance, exams

| Table | Key columns |
|---|---|
| `attendance_session` | tenant_id, campus_id, unit_id, date, period/slot, taken_by, kind (daily/period/hostel_rollcall) |
| `attendance_record` | session_id, student_id (or staff_id), status (present/absent/late/excused/leave), remark — partition candidate |
| `attendance_leaverequest` | person, dates, reason, workflow_instance_id |
| `examinations_gradingscheme` | tenant_id, institution_id, kind, bands JSONB (validated), pass_rules JSONB |
| `examinations_exam` | academic_year_id, term_id, name, components JSONB, weightage, status |
| `examinations_markentry` | exam_id, offering_id, student_id, component, marks NUMERIC, status (draft/submitted/locked), version |
| `examinations_result` | exam_id, student_id, totals, gpa, grade, position, published_at — derived, reproducible |

### 2.8 Fees & accounting (financial integrity critical)

| Table | Key columns |
|---|---|
| `fees_feehead` | tenant_id, institution_id, code, name, income_account_id |
| `fees_feestructure` / `fees_feestructureitem` | applicability (unit/year/category), heads, amounts, installments |
| `fees_invoice` | tenant_id, institution_id, student_id, number (sequence), issue_date, due_date, currency, total, status (draft/issued/partially_paid/paid/void) |
| `fees_invoiceline` | invoice_id, fee_head_id, amount, discount, net |
| `fees_concession` | student/invoice, kind (discount/scholarship/waiver), amount/percent, approved_by, workflow_instance_id |
| `fees_payment` | tenant_id, number, payer, method, gateway, gateway_ref, amount, currency, received_at, status, idempotency_key (unique per tenant) |
| `fees_paymentallocation` | payment_id, invoice_id, amount |
| `fees_refund` | payment_id, amount, reason, approved_by |
| `accounting_account` | tenant_id, institution_id, code, name, type (asset/liability/equity/income/expense), parent_id |
| `accounting_journalentry` | tenant_id, institution_id, number, date, source_type, source_id, memo, posted_at, reversal_of_id |
| `accounting_journalline` | entry_id, account_id, debit NUMERIC, credit NUMERIC, currency — constraint: sum(debit) = sum(credit) per entry (enforced in service + deferred constraint trigger) |
| `accounting_fiscalperiod` | institution_id, start, end, status (open/closed) — no postings into closed periods |

**Financial rules:**
1. Every payment, refund, concession and payroll posting creates journal entries in the **same transaction** as the source record.
2. Balance-changing operations lock affected rows (`SELECT ... FOR UPDATE`) in a consistent order to avoid deadlocks.
3. Payment endpoints require `Idempotency-Key`; webhook processing is idempotent by gateway event ID.
4. No deletes; voids and reversals only. Each posted entry is immutable (enforced by service + DB trigger rejecting UPDATE/DELETE of posted rows).
5. Gap-free receipt/invoice numbering uses a locked sequence row per scope (not PostgreSQL sequences, which can gap).

### 2.9 HR & payroll, hostel, transport, library, LMS, online exams, communication, AI

Outlined in `MODULE_CATALOG.md`; detailed schemas are defined in the plan of their phase (11–16). Fixed requirements now:
- Payroll runs are immutable once approved; posting to accounting is atomic.
- Hostel: `hostel_hostel → hostel_block → hostel_floor → hostel_room → hostel_bed`; `hostel_allocation` (student, bed, from, to, status) with exclusion constraint preventing overlapping active allocations per bed (`btree_gist`).
- Communication: `communication_message`, `communication_delivery` (partitioned), provider responses stored for audit.
- AI: `ai_conversation`, `ai_message`, `ai_toolcall` (audit), `ai_document`, `ai_chunk` (with `embedding vector(N)`, tenant_id, access metadata; HNSW index).

### 2.10 Audit & files

| Table | Key columns |
|---|---|
| `audit_auditevent` | id, occurred_at, tenant_id (nullable; dual-scope RLS in Phase 3), actor_user_id, actor_type (user/system/support/ai), support_session_id, action, outcome, target_type, target_id, metadata JSONB (allow-listed + redacted), user_agent_summary, request_id. Append-only, DB-enforced (grants + trigger); partitioning in Phase 18 |
| `audit_auditeventip` | event_id, ip_encrypted, ip_index (HMAC), ip_prefix, created_at. Deletable for retention/anonymization (ADR-036) |
| `files_file` | tenant_id, storage_key, original_name, content_type, size, checksum, uploaded_by, scan_status, retention_class |

## 3. Indexing guidelines

- Composite indexes start with `tenant_id` for tenant-filtered queries (`(tenant_id, institution_id, status)`).
- Index every FK used in joins; avoid speculative indexes.
- Partial indexes for hot subsets (`WHERE status = 'issued'`).
- GIN on JSONB only where queried by key; trigram (`pg_trgm`) for name search; FTS `tsvector` for global search.
- Review `EXPLAIN ANALYZE` for list endpoints with seeded realistic volumes (Phase 18).

## 4. Migration policy

1. One migration set per PR; reviewed for locking impact (avoid long `ACCESS EXCLUSIVE` locks on big tables — add columns nullable, backfill in batches, then constrain).
2. Expand → migrate → contract for renames/removals across releases.
3. RLS policies created by migrations for every new tenant table (helper operation `EnableTenantRLS("app_model")`: ENABLE + FORCE + `NULLIF(current_setting('app.tenant_id', true), '')::uuid` policy with `WITH CHECK`), verified by a CI test that lists tenant tables without policies (ADR-009). Migrations run as `erp_owner`; grants to `erp_app` are applied by the same helper.
4. Data migrations must be idempotent and tenant-aware.
5. No destructive migration without explicit owner approval noted in the PR.

## 5. Extensions required

`pgvector` (`vector`), `pg_trgm`, `btree_gist`, `citext`, `pgcrypto` (if DB-side UUID/crypto needed).

### Change notes
- 2026-11-05 — Initial version (Phase 0).
- 2026-11-05 — Updated for owner-approved ADR-009/010/011/012/013/014 (session auth, transaction-scoped RLS context, DB roles, UUIDv7 abstraction, tenant-level subscription with campus limits, uv/pnpm, layout).
- 2026-11-05 — Aligned with Phase 2 approvals (ADR-031 to ADR-037); see `plans/PHASE_02_PLAN.md` rev. 2.
- 2026-11-06 — Phase 2 implemented the identity/RBAC/audit tables exactly as designed in `plans/PHASE_02_PLAN.md` §7, plus `identity_sessionrecord.session_key_encrypted` (plan §18 D4). Dual-scope `tenant_id` columns exist on `rbac_role`, `rbac_rolepermission` and `audit_auditevent`; their RLS policies arrive in Phase 3.
- 2026-11-06 — ADR-040: `audit_auditevent.recorded_tx_at` (set by trigger to the writing transaction's start) and an `audit_auditeventip` guard trigger (runtime role: add IP rows only with their event; clear but never rewrite). **Never reverse the audit migrations in production**: `audit.0003` refuses reversal unless `ERP_ALLOW_AUDIT_ROLLBACK=true` outside production/staging, and reversing `audit.0001`/`0002` would remove the protection and the audit data.
