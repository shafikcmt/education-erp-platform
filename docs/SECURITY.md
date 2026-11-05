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
- Password policy: min length 10 (proposed), Django validators, optional breached-password check.
- MFA: TOTP (Phase 2); WebAuthn/passkeys later. **Mandatory** for `super_admin`, all platform roles, `tenant_owner`, `institution_admin`; tenant-configurable for others (cannot be turned off for mandated roles).
- Login: rate-limited per IP and per account; progressive delays/lockout with notification; generic error messages.
- Sessions/tokens (ADR-011 — Proposed): short-lived access token (≈10 min) + rotating refresh token (reuse detection → revoke family), stored in `HttpOnly; Secure; SameSite=Lax` cookies set by the Next.js BFF; never in `localStorage`. Mobile clients later use bearer tokens with the same rotation.
- Session list & revoke; revoke all on password change; inactivity timeout configurable per tenant.
- Phone OTP login (common in Bangladesh) is a candidate feature; requires SMS cost and abuse analysis (open question).
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

### Change notes
- 2026-11-05 — Initial version (Phase 0).
