# Security Standards

> Target: **OWASP ASVS 4.x/5.x Level 2** across the application; Level 3 controls for authentication, tenancy and finance where practical.
> Security requirements are part of the definition of done for every phase.

## 1. Threat model highlights

| Threat | Primary controls |
|---|---|
| Cross-tenant data access (IDOR, missing filter) | Tenant context + fail-closed managers + RLS + isolation tests (`MULTI_TENANT_ARCHITECTURE.md`) |
| Privilege escalation within tenant | Permission checks server-side, scoped assignments, role-change audit, cannot grant permissions one does not hold |
| Account takeover | Argon2, MFA, rate limiting, breached-password check (optional), session management, login alerts |
| Financial fraud (cash leakage, fake waivers) | Immutable ledger, approvals for concessions/refunds, segregation of duties, day-close, audit |
| Injection (SQL, template, formula) | ORM only (no raw SQL without review), sandboxed templates, CSV formula-injection escaping on export |
| XSS / CSRF | React escaping, CSP, sanitized rich text, SameSite cookies, CSRF tokens for cookie auth |
| SSRF via integrations/webhooks/files | Allow-listed outbound hosts for provider calls; no user-supplied URLs fetched server-side without validation |
| Malicious file uploads | Type/size validation, separate storage domain, presigned URLs, malware-scan hook, no execution |
| AI prompt injection / data exfiltration | Tool-only access through authorization pipeline, no cross-tenant retrieval, confirmation for writes (`AI_ASSISTANT.md`) |
| Insider/support misuse | Support sessions (time-bound, reasoned, audited, tenant-visible) |
| Secret leakage | Env/secret manager only, secret scanning in CI, no secrets in logs |

## 2. Authentication

- Password hashing: Argon2id (Django `Argon2PasswordHasher` first in `PASSWORD_HASHERS`).
- Password policy: Django password hashers and validators (ADR-033): minimum 10, maximum 128. Breached-password check (HIBP k-anonymity) is an **optional integration, disabled by default** (ADR-037).
- MFA: TOTP + single-use recovery codes (Phase 2); WebAuthn/passkeys later.
  - **Mandatory for privileged accounts** (ADR-035), defined by data: a user must have MFA if any effective permission has `requires_mfa`. This covers all platform roles, `tenant_owner`, `institution_admin`, and roles that manage roles/assignments or approve financial operations.
  - Ordinary accounts are not forced and are not asked for MFA on ordinary actions. Tenants may require it for more roles but cannot turn off the mandated ones.
  - TOTP secrets are encrypted at rest (ADR-031). Enrollment shows a server-rendered QR (ADR-037).
  - As an accessibility alternative, the **manual-entry key** can be shown **once**, only during initial enrollment and only after fresh re-authentication. It never appears in logs, analytics, emails or later responses; if it is lost before confirmation, setup restarts with a new secret (ADR-038).
  - Recovery codes are stored only as hashes.
- **Step-up re-authentication** (password + MFA, valid 10 minutes) is required for sensitive operations: password/email change, MFA changes, role grants, deactivation, admin MFA reset, revoking others' sessions, IP reveal, and future permissions flagged `requires_step_up` (ADR-035).
- Login: rate-limited per IP and per account; progressive delays/lockout with notification; generic error messages.
- **Browser sessions (ADR-011, accepted with modification):** Django session authentication for the first-party web app.
  - Session cookie: `HttpOnly; Secure; SameSite=Lax`, **host-only** (no `Domain` attribute, so a cookie for one tenant's host is never sent to another tenant's host).
  - CSRF cookie: `Secure; SameSite=Lax`, readable by JS only to send `X-CSRFToken`.
  - CSRF enforced on every unsafe method, including login/logout. `CSRF_TRUSTED_ORIGINS` limited to platform and verified tenant domains.
  - Web and API are served from the same origin through Nginx, so no CORS is needed for the web app.
  - Session key rotated on login and privilege change. `cached_db` session backend, so sessions can be listed and revoked.
  - MFA completes before the session is fully authenticated.
- **No access/refresh tokens in `localStorage`, `sessionStorage`, IndexedDB or JS-readable cookies — ever.** Next.js does not hold or mint credentials.
- **Mobile / third-party (future):** a separate OAuth 2.1-compatible token path (Authorization Code + PKCE, client credentials), with short-lived access tokens, rotating refresh tokens with reuse detection, tenant- and scope-bound tokens, revocation and audit. Mechanism to be chosen in ADR-028 (Proposed). It uses the same authorization pipeline.
- **Sessions:** 30-minute idle timeout and 12-hour absolute lifetime (ADR-037); tenant-configurable within platform bounds from Phase 3.
  - Users can list and revoke their sessions; admins can revoke a user's sessions (step-up).
  - All sessions are revoked on password reset, deactivation and admin MFA reset; other sessions are revoked on password change, email change and MFA disable.
- **No user enumeration:** login, password reset, activation resend and (Phase 3) invitations return identical responses whether or not an account exists.
- **No public registration.** Accounts are created only by authorized administrators (platform) or by invitation (tenants, Phase 3) (ADR-037).
- **Email-link tokens** (activation, verification, reset, email change) are 256-bit random, stored only as SHA-256 hashes, single-use, purpose-bound, expiring, invalidated by newer tokens and rate-limited (ADR-034).
- **New sign-in notifications** go to platform staff by policy, and contain no IP, location or tokens (ADR-037).
- Phone number / SMS-code login is **deferred to Phase 14** (ADR-037).
- Enterprise SSO (SAML/OIDC) later.

## 3. Authorization (RBAC) {#rbac}

**Model:** `Permission` (code) ← `Role` (bundle) ← `RoleAssignment` (membership + scope).

**Evaluation (`rbac.services.has_perm(actor, code, *, tenant, institution=None, campus=None, obj=None)`):**
1. Actor must have active membership in tenant (or a valid support session / platform role for platform endpoints).
2. Module of `code` must be entitled for tenant.
3. Some assignment of actor grants `code` with a scope covering the target (tenant ⊇ institution ⊇ campus).
4. Object-level policy (if defined for the resource) must allow — e.g. teacher may enter marks only for offerings they are assigned to; guardian may view only linked children; student only self.
5. Default deny.

**Rules:**
- Code checks **permissions, never role names**.
- Checks happen in DRF permission classes **and** in services (defense-in-depth; services are also called by Celery, AI tools, imports).
- Querysets for list endpoints are filtered by scope via selectors (`visible_students(actor)`), not post-filtered in Python.
- Role management: a user can only grant permissions they themselves hold, within scopes they control; changes audited.
- **Segregation of duties** (configurable, recommended defaults): the creator of a concession/refund cannot approve it; payroll preparer ≠ approver.
- Sensitive fields (e.g. medical info, guardian income, staff salary, national ID) require explicit `*.view_sensitive` permissions and are masked otherwise.

**Platform roles:** `super_admin`, `platform_support`, `platform_billing`, `platform_onboarding` — separate from tenant roles; platform endpoints live under `/api/v1/platform/` and require platform role + MFA.

## 4. Data protection & privacy

- TLS 1.2+ everywhere (HSTS). Internal service traffic on private networks.
- Encryption at rest: managed disk/DB encryption; backups encrypted; object storage SSE.
- Application-level encryption (field-level, e.g. via envelope encryption) for: integration credentials (gateway keys, SMS API keys), MFA secrets, and designated highly-sensitive fields. Key management approach decided in Phase 2/18 (open question: cloud KMS vs. self-managed).
- Minors' data: many data subjects are children → data minimization, purpose limitation, guardian visibility rules, retention policies per data class, export/deletion processes. Compliance targets (e.g. Bangladesh data-protection rules as enacted, GDPR for EU tenants) require legal review — **open question**.
- PII never in logs (structlog processors redact configured keys), never in Sentry payloads (`send_default_pii=False` + scrubbing), never sent to AI providers unless tenant opted in and minimized.
- No production data in dev/test; seed data is synthetic.

## 5. Application security controls

- Django security settings: `SECURE_*`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `X_FRAME_OPTIONS=DENY`, `SECURE_CONTENT_TYPE_NOSNIFF`.
- CSP (Nginx/Next.js): default-src 'self'; nonces for scripts; report-uri to Sentry.
- CORS: explicit allow-list (platform domains); credentials only for same-site origins.
- Rate limiting: DRF throttles (per user, per tenant, per IP) + Nginx limits; stricter on auth, public forms, OTP, AI.
- Input validation: serializers + JSON Schema for JSONB; size limits on requests/uploads.
- File uploads: allow-listed MIME/extension, max sizes, randomized keys, `Content-Disposition: attachment` for non-images, served from separate domain/bucket, scan hook.
- Exports: CSV formula injection escaping; exports generated async, stored with expiry, permission re-checked on download.
- Webhooks: HMAC/signature verification, timestamp tolerance, idempotency.
- Dependency scanning: `pip-audit`, `pnpm audit`, Dependabot; container image scanning (e.g. Trivy) in CI.
- Static analysis: ruff security rules (`S`), Bandit-equivalent; ESLint security plugins as appropriate; CodeQL (GitHub) recommended.
- Secret scanning: GitHub secret scanning + pre-commit hook (e.g. gitleaks).
- Admin: Django admin restricted to platform staff, MFA, separate path, IP allow-list in production (optional).
- **Production settings guards (implemented in Phase 1, tested):**
  - `config.settings.prod` refuses to start without `DJANGO_ALLOWED_HOSTS`.
  - It also refuses a `DJANGO_SECRET_KEY` that is shorter than 50 characters, has fewer than 5 distinct characters, or uses a `dev-`/`test-`/`change-me`/`django-insecure-` prefix.
  - `DEBUG` and the OpenAPI docs/schema are **forced off**, whatever the environment says. They stay off until platform-staff-only access exists.
  - Django's `check --deploy --fail-level WARNING` passes. Only `security.W021` (HSTS preload) is silenced, deliberately.
- **Database least privilege (implemented in Phase 1, tested):**
  - `erp_app` is NOSUPERUSER, NOBYPASSRLS, NOINHERIT with no memberships, and DML-only (no TRUNCATE/DDL); it cannot alter or drop tables or run migrations.
  - `PUBLIC` loses `CONNECT` and `TEMPORARY` on the app database; only `erp_owner` and `erp_app` may connect.
  - Passwords are stored as SCRAM-SHA-256.

## 6. Audit logging

Audit (append-only, `audit_event`) is mandatory for:
- Authentication events (login, failure, MFA changes, password reset, session revoke).
- Role/permission changes, membership changes.
- Tenant/plan/entitlement changes, Super Admin actions, support sessions.
- All financial operations (invoice issue/void, payment, refund, concession, journal post, period close, payroll approve).
- Exam marks lock/unlock, result publish/unpublish.
- Customization publishes (with diff).
- Exports of personal data; viewing of sensitive fields.
- AI tool calls.

**Never logged** (audit, application logs, Sentry, emails): passwords, password hashes, email-link tokens, MFA secrets/QR payloads, MFA codes, recovery codes, session keys, CSRF tokens. Audit metadata is built from per-event allow-lists, and leak tests run for every auth flow (Phase 2 plan §6.8).

**IP addresses (ADR-036):**
- Encrypted at rest, with a keyed blind index for exact-match search.
- Masked in the UI by default; revealing one requires `audit.event.view_ip` + step-up and is itself audited.
- Retention is configurable (default 365 days, **pending legal review**), after which a job anonymizes them to a network prefix. A documented `erase_ip_data` procedure handles data-subject requests.
- Audit-event IPs live in a separate, deletable side table, so the audit log itself stays immutable.

Audit records: never updated or deleted by application code; DB role for app has INSERT-only on audit tables; retention per policy (proposed ≥ 7 years for financial, ≥ 1 year for others — **owner/legal confirmation needed**).

## 7. Secrets & configuration

- 12-factor: configuration via environment variables; `.env.example` documents keys with dummy values; real `.env` files are git-ignored.
- Production secrets in a secret manager (GitHub Actions secrets/environments for CI/CD; host secret store for runtime).
- Per-tenant integration credentials encrypted in DB (never returned to clients after save).
- Rotate on suspicion; document rotation steps in `DOCKER_DEPLOYMENT.md`.

## 8. Backups & disaster recovery

- PostgreSQL: continuous WAL archiving + scheduled base backups (tool: pgBackRest or WAL-G — decision in Phase 19), encrypted, stored off-site (different provider/region).
- PITR capability; proposed RPO ≤ 15 min, RTO ≤ 4 h.
- Object storage: versioning + lifecycle; cross-region replication for production (if provider supports).
- Redis: treated as ephemeral (no source-of-truth data).
- **Restore drills** at least quarterly, documented with results in `DEVELOPMENT_PROGRESS.md` (or ops log).
- Per-tenant logical export for portability and targeted recovery.

## 9. Monitoring & incident response

- Sentry for errors/performance (backend + frontend), release tracking, PII scrubbing.
- Structured JSON logs with `request_id`, `tenant_id`, `user_id`, `module`; centralized log storage (choice in Phase 19).
- Security alerts: spikes in auth failures, permission denials, cross-tenant access attempts (TenantMismatch errors are high-severity alerts), unusual exports.
- Incident response runbook (Phase 18): triage, containment, tenant notification obligations, post-mortem.

## 10. Security checklist per PR (copy into PR description when relevant)

- [ ] Tenant isolation preserved (tenant-scoped models, selectors, isolation tests added)
- [ ] Permissions enforced server-side (allowed + denied tests)
- [ ] Module entitlement enforced
- [ ] Input validated; output encoded; no raw SQL (or reviewed)
- [ ] Financial ops atomic, idempotent, audited (if applicable)
- [ ] No secrets/PII in code, logs, tests, fixtures
- [ ] Migrations reviewed (locks, RLS policy added for new tenant tables)
- [ ] New dependencies justified and scanned

## 11. Phase 2 implementation map and operating procedures

| Control | Where |
|---|---|
| Field encryption / blind index | `apps/core/crypto.py`, `apps/core/ip_privacy.py` |
| Equal-work authentication backend | `apps/identity/backends.py` |
| Throttles, progressive delay, lock | `apps/identity/throttling.py`, `services/auth.py` |
| MFA, manual key, recovery codes | `apps/identity/services/mfa.py` |
| Sessions, timeouts, revocation | `apps/identity/middleware.py`, `services/sessions.py` |
| Permission engine and DRF classes | `apps/rbac/engine.py`, `sources.py`, `permissions.py` |
| Append-only audit | `apps/audit/migrations/0002_append_only.py`, `apps/audit/services.py` |
| Every API view authorized | `backend/tests/test_url_authorization_audit.py` |
| No secret leakage | `backend/tests/test_no_secret_leakage.py` |

**Bootstrap the first Super Admin** (no default credentials):
`docker compose exec api python manage.py create_platform_admin --email owner@your-domain`.
The activation link arrives by email; the owner sets a password and must enrol MFA before using the console.

**Rotate the field-encryption key (ADR-031):** generate a key (`python -c "from apps.core.crypto import generate_key; print(generate_key())"`), put `newid:<key>` **first** in `FIELD_ENCRYPTION_KEYS` while keeping the old entries, deploy, run `manage.py rotate_field_encryption`, verify sign-in with MFA, then remove the old key.

**Rotate `IP_INDEX_KEY` (ADR-036):** set the new key, deploy, run `manage.py rebuild_ip_index`.

**Erase a person's IP data (data-subject request):** `manage.py erase_ip_data --user <uuid> [--before YYYY-MM-DD]`. It deletes the person's audit IP rows and clears the IP fields of their session records; the audit events stay, and the erasure itself is audited.

**Key loss:** MFA secrets and stored IPs become unreadable. Users recover with recovery codes or an admin MFA reset; keys must therefore be backed up in the secret manager (Phase 19).

### Change notes
- 2026-11-05 — Initial version (Phase 0).
- 2026-11-05 — Updated for owner-approved ADR-009/010/011/012/013/014 (session auth, transaction-scoped RLS context, DB roles, UUIDv7 abstraction, tenant-level subscription with campus limits, uv/pnpm, layout).
- 2026-11-05 — Phase 1 review: production guards and database least-privilege controls documented as implemented.
- 2026-11-05 — Aligned with Phase 2 approvals (ADR-031 to ADR-037); see `plans/PHASE_02_PLAN.md` rev. 2.
- 2026-11-06 — Manual MFA key exception (ADR-038) documented.
- 2026-11-06 — Phase 2 implemented: implementation map and operating procedures added (§11).
