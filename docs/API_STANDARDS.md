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

- Browser: cookie-based tokens via Next.js BFF (ADR-011 proposed); CSRF protection for unsafe methods.
- Programmatic/mobile (later): `Authorization: Bearer <token>`; tenant API keys for enterprise integrations (scoped permissions, rotatable, audited).
- `X-Request-ID` accepted/generated and echoed; included in logs and error bodies.
- `Accept-Language` for localization; tenant default otherwise.
- `X-Tenant` only for non-host-based clients and only alongside a token whose membership is verified.

## 8. Authorization in views

Every view declares:
```python
permission_classes = [IsAuthenticated, TenantMember, ModuleEntitled("students"), HasPermission("students.student.view")]
```
plus a scoped queryset from selectors (`selectors.visible_students(actor=request.actor)`). Services re-check permissions for writes. A CI test enumerates all URL patterns and fails if a tenant endpoint lacks `ModuleEntitled` and `HasPermission` (or an explicit, reviewed exemption).

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
