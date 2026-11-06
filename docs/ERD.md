# Entity-Relationship Diagrams

> Target design (Mermaid). Tables are implemented phase by phase. Column details: `DATABASE_DESIGN.md`.
> Every tenant-owned entity has `tenant_id` (omitted from some diagrams for readability, but always present).

## 1. Platform: tenancy, identity, RBAC

```mermaid
erDiagram
  TENANT ||--o{ TENANT_DOMAIN : "has"
  TENANT ||--o{ INSTITUTION : "owns"
  INSTITUTION ||--o{ CAMPUS : "has"
  USER ||--o{ MEMBERSHIP : "belongs via"
  TENANT ||--o{ MEMBERSHIP : "has"
  MEMBERSHIP ||--o{ ROLE_ASSIGNMENT : "granted"
  ROLE ||--o{ ROLE_ASSIGNMENT : "assigned as"
  ROLE ||--o{ ROLE_PERMISSION : "contains"
  PERMISSION ||--o{ ROLE_PERMISSION : "in"
  INSTITUTION |o--o{ ROLE_ASSIGNMENT : "scope"
  CAMPUS |o--o{ ROLE_ASSIGNMENT : "scope"
  TENANT ||--o{ SUPPORT_SESSION : "audited access"
  USER ||--o{ SUPPORT_SESSION : "platform staff"

  TENANT { uuid id PK  string slug UK  string status  string timezone  string currency }
  INSTITUTION { uuid id PK  uuid tenant_id FK  string institution_type  string preset_code }
  CAMPUS { uuid id PK  uuid institution_id FK  bool is_main }
  USER { uuid id PK  citext email UK  bool is_platform_staff }
  MEMBERSHIP { uuid id PK  uuid tenant_id FK  uuid user_id FK  string status }
  ROLE { uuid id PK  uuid tenant_id "nullable = template"  string code }
  PERMISSION { string code PK  string module_code }
  ROLE_ASSIGNMENT { uuid id PK  uuid membership_id FK  uuid role_id FK  string scope_type }
```

## 2. Module registry, billing, customization

```mermaid
erDiagram
  PLAN ||--o{ PLAN_MODULE : "includes"
  MODULE ||--o{ PLAN_MODULE : "in"
  MODULE ||--o{ ADDON : "sold as"
  PLAN ||--o{ PRICE : "priced"
  ADDON ||--o{ PRICE : "priced"
  TENANT ||--o| SUBSCRIPTION : "has current"
  PLAN ||--o{ SUBSCRIPTION : "for"
  SUBSCRIPTION ||--o{ SUBSCRIPTION_ITEM : "add-ons"
  ADDON ||--o{ SUBSCRIPTION_ITEM : "is"
  TENANT ||--o{ TENANT_MODULE : "entitled (resolved)"
  MODULE ||--o{ TENANT_MODULE : "enabled as"
  TENANT ||--o{ USAGE_RECORD : "metered"
  TENANT ||--o{ SAAS_INVOICE : "billed"
  SAAS_INVOICE ||--o{ SAAS_PAYMENT : "paid by"

  PRESET ||--o{ CONFIG_SET : "base for"
  TENANT ||--o{ CONFIG_SET : "overrides"
  TENANT ||--o{ CUSTOM_FIELD_DEF : "defines"
  TENANT ||--o{ FORM_DEF : "defines"
  TENANT ||--o{ WORKFLOW_DEF : "defines"
  WORKFLOW_DEF ||--o{ WORKFLOW_INSTANCE : "runs"
  TENANT ||--o{ RULE : "defines"
  TENANT ||--o{ TEMPLATE : "defines"
  TENANT ||--o{ NUMBER_SEQUENCE : "defines"
```

## 3. Academics, admissions, people

```mermaid
erDiagram
  INSTITUTION ||--o{ ACADEMIC_YEAR : "runs"
  ACADEMIC_YEAR ||--o{ TERM : "divided into"
  INSTITUTION ||--o{ STRUCTURE_LEVEL : "configures"
  STRUCTURE_LEVEL ||--o{ ACADEMIC_UNIT : "typed by"
  ACADEMIC_UNIT |o--o{ ACADEMIC_UNIT : "parent of"
  CAMPUS ||--o{ ACADEMIC_UNIT : "hosts"
  INSTITUTION ||--o{ SUBJECT : "teaches"
  ACADEMIC_UNIT ||--o{ OFFERING : "offers"
  SUBJECT ||--o{ OFFERING : "offered as"
  TERM |o--o{ OFFERING : "in"
  STAFF ||--o{ TEACHING_ASSIGNMENT : "assigned"
  OFFERING ||--o{ TEACHING_ASSIGNMENT : "taught by"

  INSTITUTION ||--o{ ADMISSION_CYCLE : "opens"
  ADMISSION_CYCLE ||--o{ APPLICATION : "receives"
  APPLICATION |o--o| STUDENT : "converts to"

  STUDENT ||--o{ STUDENT_GUARDIAN : "has"
  GUARDIAN ||--o{ STUDENT_GUARDIAN : "of"
  STUDENT ||--o{ ENROLLMENT : "enrolled"
  ACADEMIC_YEAR ||--o{ ENROLLMENT : "for"
  ACADEMIC_UNIT ||--o{ ENROLLMENT : "in"
  USER |o--o| STUDENT : "login"
  USER |o--o| GUARDIAN : "login"
  USER ||--o| STAFF : "login"
```

## 4. Attendance and examinations

```mermaid
erDiagram
  ACADEMIC_UNIT ||--o{ ATTENDANCE_SESSION : "taken for"
  ATTENDANCE_SESSION ||--o{ ATTENDANCE_RECORD : "contains"
  STUDENT ||--o{ ATTENDANCE_RECORD : "marked"
  STUDENT ||--o{ LEAVE_REQUEST : "requests"

  INSTITUTION ||--o{ GRADING_SCHEME : "defines"
  TERM ||--o{ EXAM : "holds"
  GRADING_SCHEME ||--o{ EXAM : "graded by"
  EXAM ||--o{ MARK_ENTRY : "records"
  OFFERING ||--o{ MARK_ENTRY : "for"
  STUDENT ||--o{ MARK_ENTRY : "scores"
  EXAM ||--o{ RESULT : "produces"
  STUDENT ||--o{ RESULT : "receives"
```

## 5. Fees and accounting

```mermaid
erDiagram
  INSTITUTION ||--o{ FEE_HEAD : "defines"
  FEE_HEAD }o--|| ACCOUNT : "income account"
  FEE_STRUCTURE ||--o{ FEE_STRUCTURE_ITEM : "contains"
  FEE_HEAD ||--o{ FEE_STRUCTURE_ITEM : "priced in"
  STUDENT ||--o{ INVOICE : "billed"
  INVOICE ||--o{ INVOICE_LINE : "contains"
  FEE_HEAD ||--o{ INVOICE_LINE : "for"
  INVOICE ||--o{ CONCESSION : "reduced by"
  PAYMENT ||--o{ PAYMENT_ALLOCATION : "allocated"
  INVOICE ||--o{ PAYMENT_ALLOCATION : "settled by"
  PAYMENT ||--o{ REFUND : "refunded"

  INSTITUTION ||--o{ ACCOUNT : "chart of accounts"
  ACCOUNT |o--o{ ACCOUNT : "parent"
  JOURNAL_ENTRY ||--|{ JOURNAL_LINE : "balanced lines"
  ACCOUNT ||--o{ JOURNAL_LINE : "posted to"
  JOURNAL_ENTRY |o--o| JOURNAL_ENTRY : "reversal of"
  PAYMENT ||--o{ JOURNAL_ENTRY : "source"
  REFUND ||--o{ JOURNAL_ENTRY : "source"
  FISCAL_PERIOD ||--o{ JOURNAL_ENTRY : "dated in"
```

## 6. Hostel engine

```mermaid
erDiagram
  CAMPUS ||--o{ HOSTEL : "has"
  HOSTEL ||--o{ HOSTEL_BLOCK : "has"
  HOSTEL_BLOCK ||--o{ HOSTEL_FLOOR : "has"
  HOSTEL_FLOOR ||--o{ HOSTEL_ROOM : "has"
  HOSTEL_ROOM ||--o{ HOSTEL_BED : "has"
  HOSTEL }o--|| HOSTEL_PROFILE : "configured by"
  STUDENT ||--o{ HOSTEL_APPLICATION : "applies"
  HOSTEL_APPLICATION |o--o| HOSTEL_ALLOCATION : "results in"
  HOSTEL_BED ||--o{ HOSTEL_ALLOCATION : "occupied by (no overlap)"
  STUDENT ||--o{ HOSTEL_ALLOCATION : "resides"
  STUDENT ||--o{ HOSTEL_OUTPASS : "requests"
  GUARDIAN |o--o{ HOSTEL_OUTPASS : "authorizes"
  HOSTEL ||--o{ HOSTEL_VISITOR_LOG : "records"
  HOSTEL ||--o{ MEAL_PLAN : "offers"
  STUDENT ||--o{ MEAL_SUBSCRIPTION : "subscribes"
  MEAL_PLAN ||--o{ MEAL_SUBSCRIPTION : "of"
```

## 7. Audit, files, AI

```mermaid
erDiagram
  TENANT |o--o{ AUDIT_EVENT : "scoped to"
  USER |o--o{ AUDIT_EVENT : "actor"
  SUPPORT_SESSION |o--o{ AUDIT_EVENT : "during"
  TENANT ||--o{ FILE : "stores"
  TENANT ||--o{ AI_CONVERSATION : "has"
  USER ||--o{ AI_CONVERSATION : "started"
  AI_CONVERSATION ||--o{ AI_MESSAGE : "contains"
  AI_MESSAGE ||--o{ AI_TOOL_CALL : "invokes"
  TENANT ||--o{ AI_DOCUMENT : "indexed"
  AI_DOCUMENT ||--o{ AI_CHUNK : "split into (vector)"
  FILE |o--o| AI_DOCUMENT : "source"
```

### Change notes
- 2026-11-05 — Initial version (Phase 0).
- 2026-11-06 — Phase 2 implemented the identity/RBAC/audit tables exactly as designed in `plans/PHASE_02_PLAN.md` §7, plus `identity_sessionrecord.session_key_encrypted` (plan §18 D4). Dual-scope `tenant_id` columns exist on `rbac_role`, `rbac_rolepermission` and `audit_auditevent`; their RLS policies arrive in Phase 3.
