# Customization Engine & Customization Studio

> Implements the three customization levels in `CLAUDE.md` §4 and the Studio in §6.
> Golden rule: **tenants configure; they never get a different codebase and never run their own code.**

## 1. Levels

| Level | Content | Storage | Changed by |
|---|---|---|---|
| **L1 Core** | Module code, default behavior, base schemas, default settings | Code + `manifest.settings_schema` defaults | Platform engineering (PR + release) |
| **L2 Institution-type preset** | Terminology, structure levels, grading presets, default roles, default modules, report/ID/certificate templates, fee head templates, chart of accounts template, hostel profile, capability flags | `customization_preset` (versioned, platform-managed; seeded from files in repo `backend/apps/customization/presets/*.yaml`) | Platform team via PR |
| **L3 Tenant extensions** | Overrides & additions: terminology, custom fields, forms, workflows, rules, templates, numbering, dashboards, custom entities (Phase 17) | `customization_*` tables, tenant-scoped, versioned | Tenant admins in Studio (permission-gated) or platform team for enterprise |

## 2. Configuration resolution

```
effective(key, scope) =
    core_default(key)
  ⊕ preset(institution.preset_code, preset_version)(key)
  ⊕ tenant_published(key)
  ⊕ institution_published(key)
  ⊕ campus_published(key)
```

- `⊕` = deep-merge for objects; replace for scalars/lists unless a key's schema declares a merge strategy.
- Only **published** versions participate; drafts are visible only in Studio preview.
- Every setting key is declared in a module's `settings_schema` (JSON Schema) with: type, default, allowed scopes (tenant/institution/campus), whether tenant-editable, and required permission. **Undeclared keys are rejected.**
- Resolved config is cached per (tenant, scope, config version) and invalidated on publish.
- Code reads config via `get_effective_config(scope, "module.key")` — never reads raw config tables.

## 3. Institution-type presets

Preset code format: `<institution_type>.<variant>.v<N>` e.g. `school.general.v1`, `university.credit.v1`, `madrasa.qawmi.v1`, `madrasa.alia.v1`, `madrasa.hifz.v1`, `coaching.general.v1`, `training.general.v1`, `college.hsc.v1`.

A preset defines:

| Area | Example (madrasa.qawmi.v1) | Example (university.credit.v1) |
|---|---|---|
| Structure levels | Marhala → Jamaat | Faculty → Department → Program → (Semester) |
| Terminology | class→Jamaat, subject→Kitab, principal→Muhtamim | class→Program, subject→Course, principal→Vice-Chancellor/Registrar (configurable) |
| Capability flags | `hostel.residential_default=true`, `academics.credit_based=false` | `academics.credit_based=true`, `academics.semester_based=true` |
| Grading preset | Division/marks based (configurable) | 4.0 GPA/CGPA scale |
| Default roles | Muhtamim, Nazim (hostel), Ustad (teacher) as labels on standard role templates | Registrar, Controller of Exams, Dept Head, Provost |
| Default modules suggested | students, attendance, examinations, fees, hostel, ext_hifz_tracking | academics, admissions, examinations, fees, accounting, hostel, ext_course_registration |
| Templates | Result sheet, ID card | Transcript, grade sheet, admit card |
| Hostel profile | `hostel.madrasa_residential` | `hostel.university_hall` |
| Calendar | Configurable (may follow Hijri-based session — display support for Hijri dates is a proposed requirement) | Semester calendar |

> Preset content above is illustrative; actual preset content is drafted and approved in Phase 5 (and refined per module phase). Madrasa conventions vary widely (Qawmi boards, Alia, Hifz-only) — never hardcode one board's rules; express them as preset data.

**Preset upgrades:** institutions pin `preset_version`. A new preset version never changes existing tenants automatically; tenants (or platform for them) review a diff and opt in. Tenant overrides are preserved.

## 4. Studio artefacts

### 4.1 Terminology
Per locale key/value overrides (e.g. `academics.unit.section` → "Jamaat" in `en`, "জামাত" in `bn`). The frontend loads resolved terminology into i18n messages.

### 4.2 Custom fields
- Supported entities are declared in code (registry): `students.student`, `students.guardian`, `staff.staff`, `admissions.application`, `fees.invoice`, `hostel.allocation`, … Only declared entities accept custom fields.
- Field types: text, long_text, number, decimal, date, boolean, single_select, multi_select, email, phone, file, reference (to a permitted entity).
- Definition: key (immutable), labels (i18n), type, validation (JSON Schema subset), required, default, visibility (internal/portal/public form), `permission_code` for view/edit (e.g. sensitive medical info), PII flag, searchable flag, order/section.
- Values stored in the entity's `extra` JSONB under the field key; validated server-side on every write against the active definition version.
- Changing a field type is not allowed; deprecate and create a new field (data migration tool provided).
- Limits per plan (number of custom fields per entity).

### 4.3 Forms
Layout of core + custom fields into sections/steps, conditional visibility (safe expressions), used for admission/inquiry/leave/hostel application. Public forms expose only fields marked public and are rate-limited + bot-protected.

### 4.4 Workflows
Declarative state machine: states, transitions, guards (rules), required permission per transition, approver resolution (role in scope, specific user, guardian), SLA/escalation timers (Celery beat), actions on transition (emit domain event, notify). Instances pin the definition version they started with.

### 4.5 Rules (ADR-016 — Proposed)
- Safe, side-effect-free expressions stored as JSON (JSONLogic-style AST) evaluated by a vetted, sandboxed evaluator with an allow-listed operation set and a fixed set of context variables per rule namespace (e.g. `fees.late_fine` gets `invoice.due_date`, `today`, `invoice.balance`).
- No loops, no I/O, no imports, execution time/size limits.
- Used for: late fines, discount eligibility, promotion criteria, pass/fail, attendance thresholds, hostel eligibility, form visibility, workflow guards, payroll components.
- Each rule namespace has test cases; Studio provides "test with sample data" before publish.

### 4.6 Templates
- Kinds: report card, transcript, admit card, ID card, certificate, receipt, invoice, SMS, email, notice.
- Engine: sandboxed template rendering (proposed: Django template engine in a restricted sandboxed environment or Jinja2 `SandboxedEnvironment`; decide in Phase 5) with an explicit data context per template kind; no access to ORM or arbitrary attributes.
- PDF rendering via HTML→PDF in a worker (library chosen in Phase 9 — candidates: WeasyPrint; must support Bengali/Arabic shaping — verify before choosing).
- Assets (logos, signatures, backgrounds) stored via `files`.

### 4.7 Numbering sequences
Pattern tokens: `{INST}`, `{CAMPUS}`, `{YYYY}`, `{YY}`, `{AY}` (academic year), `{SEQ:n}`. Scope (tenant/institution/campus/year). Gap-free sequences (receipts) allocate under row lock within the business transaction.

### 4.8 Dashboards & report layouts
Choose widgets/reports from permitted catalogs; arrange per role. Data access always re-checked server-side.

### 4.9 Custom entities (Phase 17)
Tenant-defined entity types with fields (custom field types), list/detail/form views, permissions (generated `custom.<entity>.<action>` codes), workflows, and reports. Stored in a generic `custom_record` table (tenant_id, entity_type, data JSONB, indexed fields). Fully subject to RLS, RBAC, audit and quotas.

## 5. Versioning & publishing

| State | Meaning |
|---|---|
| `draft` | Editable; preview only |
| `published` | Active; immutable |
| `archived` | Superseded; retained for history/rollback and for records pinned to it |

- Publish requires `customization.config.publish` permission, server validation (schema, references, rule tests), and creates an audit event with a diff.
- Rollback = publish a copy of a previous version as new version (history is never rewritten).
- Records created under a definition version keep a reference to it where interpretation depends on it (workflow instances, form submissions, rule-based computations).

## 6. Hostel profiles {#hostel-profiles}

A hostel profile is an L2 preset fragment consumed by the `hostel` module; tenants override in Studio.

| Setting | `hostel.madrasa_residential` default | `hostel.university_hall` default |
|---|---|---|
| `allocation.policy` | manual / rule (age, level, gender) | application + merit / lottery |
| `tenure` | academic year, auto-renew | semester or academic year |
| `rollcall.schedule` | multiple per day (e.g. after Fajr, after Maghrib, night) — configurable list | none or nightly (optional) |
| `curfew` | enabled | optional |
| `outpass.workflow` | warden approval + guardian confirmation required | self-declared or house-tutor approval |
| `visitors.mode` | approved-visitor list, visiting days/hours | visitor log, hours |
| `meals.enabled` | yes, plans mandatory | optional |
| `gender_segregation` | strict, per hostel | per hall |
| `fees.billing_cycle` | monthly | per semester |
| `staff_roles_terms` | Nazim / Superintendent | Provost / House Tutor |

These are proposed defaults to be validated with real institutions before Phase 12.

## 7. Safety rules (non-negotiable)

1. No tenant-supplied executable code (Python/JS/SQL) — ever.
2. All Studio writes are permission-checked, tenant-scoped, validated, versioned and audited.
3. Custom fields/entities obey RLS, RBAC and field-level permissions like core data.
4. Studio changes cannot weaken platform security settings (e.g. cannot disable MFA mandated by platform policy, cannot grant permissions outside the tenant's entitled modules).
5. Quotas per plan prevent abuse (fields, forms, workflows, templates, custom entities, records).

### Change notes
- 2026-11-05 — Initial version (Phase 0).
