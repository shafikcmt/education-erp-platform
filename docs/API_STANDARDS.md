# API Standards

> Django REST Framework, OpenAPI 3 via `drf-spectacular`. The OpenAPI schema is the contract; the frontend TypeScript client is generated from it (`packages/api-client`).

## 1. Base URLs & versioning

| Area | Prefix | Audience |
|---|---|---|
| Tenant API | `/api/v1/` | Authenticated tenant users (tenant resolved from host) |
| Platform API | `/api/v1/platform/` | Platform staff (Super Admin, support, billing) |
| Public tenant API | `/api/v1/public/` | Unauthenticated, tenant resolved by host (admission forms, certificate verification) — explicitly allow-listed resources only |
| Webhooks | `/api/webhooks/<provider>/` | Payment/SMS providers (signature verified) |
| Health | `/healthz` (liveness), `/readyz` (readiness) | Infrastructure |
| Schema/docs | `/api/schema/`, `/api/docs/` | Non-production, or platform-staff-only in production |

- URL versioning (`v1`). Breaking changes → `v2` for affected endpoints; deprecations announced with `Deprecation`/`Sunset` headers.
- Non-breaking additions (new optional fields, endpoints) allowed within a version.

## 2. Resource design

- Plural nouns, kebab-case paths: `/api/v1/students/`, `/api/v1/fee-invoices/{id}/`.
- Nested routes only for strong ownership and max one level: `/api/v1/students/{id}/guardians/`.
- Actions that are not CRUD use sub-resources with verbs: `POST /api/v1/fee-invoices/{id}/void/`, `POST /api/v1/exams/{id}/publish-results/`.
- IDs: UUID strings. Never expose sequential internal IDs.
- JSON fields: `snake_case`. Dates `YYYY-MM-DD`; datetimes ISO-8601 UTC with `Z`; money as **string decimal** + currency: `{"amount": "1250.00", "currency": "BDT"}` (never JSON numbers for money).
- Custom field values under `extra` object, validated server-side.
- Translatable names: `name` (in request locale) + optional `name_i18n`.

## 3. Methods & status codes

| Method | Use | Success |
|---|---|---|
| GET | read | 200 |
| POST | create / action | 201 (create) / 200 or 202 (action/async) |
| PATCH | partial update | 200 |
| PUT | full replace (rare) | 200 |
| DELETE | delete/archive | 204 |

Errors: 400 validation, 401 unauthenticated, 403 forbidden (permission / `module_not_entitled` / `limit_exceeded`), **404 for objects outside tenant or scope** (do not reveal existence), 409 conflict (version mismatch, state conflict, duplicate idempotency key with different payload), 412 precondition failed (If-Match), 422 business rule violation, 429 rate limited, 5xx server.

## 4. Error format (RFC 9457 Problem Details style)

```json
{
  "type": "https://docs.<platform-domain>/errors/validation_error",
  "title": "Validation failed",
  "status": 400,
  "code": "validation_error",
  "detail": "One or more fields are invalid.",
  "errors": [{"field": "date_of_birth", "code": "invalid", "message": "Enter a valid date."}],
  "request_id": "01J...."
}
```

- `code` is stable and machine-readable (`validation_error`, `permission_denied`, `module_not_entitled`, `limit_exceeded`, `not_found`, `conflict`, `business_rule_violation`, `rate_limited`, `tenant_suspended`).
  - Phase 2 adds: `not_authenticated` (401, `WWW-Authenticate: Session`), `invalid_credentials`, `invalid_mfa_code`, `mfa_challenge_expired`, `mfa_required`, `mfa_enrollment_required`, `mfa_required_for_account`, `mfa_already_enrolled`, `step_up_required`, `manual_key_already_shown` (410), `invalid_token`, and guard-rail codes `privilege_escalation`, `last_super_admin`, `system_role_read_only`, `role_in_use`, `cannot_deactivate_self`, `already_activated`.
  - `rate_limited` bodies carry `retry_after` (seconds) and a `Retry-After` header.
  - Security review (ADR-040) adds: `mfa_locked` (429, `retry_after`), `insufficient_privilege` (403, acting on a more privileged account), `cannot_reset_own_mfa` (409).
  - `POST /auth/step-up/` accepts `recovery_code` instead of `code` (single use).
  - Phase 3 M3 adds, on tenant hosts only (403): `tenant_suspended`, `not_a_member`, `membership_inactive`, `tenant_unavailable` (write during offboarding). Sign-in refusals on a tenant host always use `invalid_credentials`.
  - **Uniform 404:** an unknown path, a host that is not served, an unknown or unusable tenant, and an endpoint that is not available on the request's kind of host (platform or tenant) all return the same `not_found` body. Clients cannot tell them apart.
  - On tenant hosts every response with status ≥ 400 means the request changed nothing (its transaction was rolled back).
- API responses carry `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`.
- All `/api/` responses carry `Cache-Control: no-store` unless a view sets its own policy.
- Messages localized by `Accept-Language`; never include stack traces, SQL or other tenants' data.

## 5. Pagination, filtering, sorting, search

- Default: **cursor pagination** for large/append-heavy lists (attendance, audit, payments); page-number pagination allowed for admin tables needing page jumps. Max `page_size` 100 (default 25).
- Response envelope: `{"results": [...], "next": "...", "previous": "...", "count": n?}` (`count` omitted for cursor lists where expensive).
- Filtering: `django-filter` query params (`?status=active&academic_year=<uuid>`); date ranges `created_after`, `created_before`.
- Sorting: `?ordering=-created_at,name` against an allow-list.
- Search: `?search=` using indexed fields only.
- Field selection (`?fields=`) and expansion (`?expand=guardians`) only where explicitly supported.

## 6. Concurrency & idempotency

- Optimistic locking: resources with `version` return `ETag`; updates require `If-Match` → 412 on mismatch (marks entry, timetable, config drafts).
- **`Idempotency-Key` header required** for: payment collection, refunds, invoice issuance, payroll approval/payment, SMS bulk sends, any endpoint creating money movements. Keys stored per tenant + endpoint + actor for 24 h+; same key + same payload → original response; same key + different payload → 409.
- Long operations (imports, bulk SMS, payroll runs, large reports) return `202 Accepted` with a job resource: `GET /api/v1/jobs/{id}/` (status, progress, result file link).

## 7. Authentication & headers

- **Browser (ADR-011, accepted):** Django session cookie (`HttpOnly; Secure; SameSite=Lax`, host-only) via DRF `SessionAuthentication`.
  - Unsafe methods require the `X-CSRFToken` header (value taken from the CSRF cookie); the frontend sends `credentials: 'include'`.
  - Endpoints (Phase 2):
    - Auth: `GET /auth/csrf/`, `POST /auth/login/`, `POST /auth/mfa/verify/`, `POST /auth/logout/`, `POST /auth/step-up/`.
    - Account flows: password reset (+ confirm), activation (+ resend), email verify.
    - Self-service and administration: `/me/*` and `/platform/*`.
    - The full table is in `plans/PHASE_02_PLAN.md` §8.
  - Sensitive operations return `403 step_up_required` until the user re-authenticates (ADR-035).
  - Auth responses never reveal whether an account exists.
- **Programmatic/mobile (future, ADR-028 Proposed):** `Authorization: Bearer <token>` issued through a separate OAuth 2.1-compatible path. Tenant API keys for enterprise integrations (scoped permissions, rotatable, audited).
- Authentication classes are pluggable; every authentication method feeds the **same** authorization pipeline.
- `X-Request-ID` accepted/generated and echoed; included in logs and error bodies.
- `Accept-Language` for localization; tenant default otherwise.
- `X-Tenant` only for non-host-based clients and only alongside a token whose membership is verified.

## 8. Authorization in views

Every view declares:
```python
permission_classes = [IsAuthenticated, TenantMember, ModuleEntitled("students"), HasPermission("students.student.view")]
```
plus a scoped queryset from selectors (`selectors.visible_students(actor=request.actor)`). Services re-check permissions for writes. A CI test enumerates all URL patterns and fails if a tenant endpoint lacks `ModuleEntitled` and `HasPermission` (or an explicit, reviewed exemption).

**Implemented so far (Phase 3 M8):** tenant-host views declare `host_classes = TENANT_ONLY` and use `HasTenantPermission(...)` (the code held in any scope of the tenant) when their objects live in narrower scopes; the view filters lists to the actor's scopes, answers objects outside them with 404, and the service re-checks the exact scope. Platform-host views of tenant registry operations declare `platform_operations = {"METHOD": "P…"}`. `ModuleEntitled` arrives with Phase 4. Reviewed lists in tests: tenant-host routes, anonymous/session-only routes, suspended-tenant routes.

## 9. Rate limits (proposed defaults, tunable)

| Scope | Limit |
|---|---|
| Login / OTP / password reset | strict per IP + per identifier (e.g. 5/min) |
| Public forms | per IP + CAPTCHA/bot protection |
| Authenticated API | per user and per tenant burst/sustained |
| AI endpoints | per user + tenant quota |
| Exports | concurrent job limit per tenant |

## 10. Documentation & schema rules

- Every endpoint has `@extend_schema` with summary, tags (module code), request/response serializers and error responses.
- CI checks: schema generation succeeds with **zero warnings**; committed client is regenerated (drift check).
- Examples use synthetic data only.

## 11. Webhooks (inbound)

- Verify signature + timestamp; reject replays.
- Persist raw event (`webhook_event`: provider, event_id unique, payload, received_at, processed_at, status).
- Acknowledge fast (2xx), process async and idempotently; reconcile periodically against provider APIs.

### Change notes
- 2026-11-05 — Initial version (Phase 0).
- 2026-11-05 — Updated for owner-approved ADR-009/010/011/012/013/014 (session auth, transaction-scoped RLS context, DB roles, UUIDv7 abstraction, tenant-level subscription with campus limits, uv/pnpm, layout).
- 2026-11-05 — Aligned with Phase 2 approvals (ADR-031 to ADR-037); see `plans/PHASE_02_PLAN.md` rev. 2.
- 2026-11-06 — Phase 2 implemented: authentication error codes, 401 challenge and `no-store` documented.
- 2026-11-06 — ADR-040 error codes, step-up `recovery_code` and the API CSP documented.
- 2026-11-13 — Phase 3 M3: tenant-host error codes, the uniform 404 and the rollback rule documented.
- 2026-11-19 — Phase 3 M8: what §8 looks like in the implemented tenancy API.
