# Phase 3 — Security Self-Review (M11)

- **Status:** self-review by the implementing engineer, **not** an independent review. Plan §10.2 (D1) requires the owner's approved security review before tenant hosts can be enabled in production; this document is input to it.
- **Date:** 2026-11-21. **Scope:** Phase 3 as merged in PRs #17, #18 and #29–#36, plus the M10 part 2 branch (`feat/phase-03-m10b`).
- **Method:**
  1. Walk the threat model (plan §14) and the §23 checklist against code and tests. Evidence: `docs/security/PHASE_03_ISOLATION_EVIDENCE.md`.
  2. Re-read the new attack surface of each milestone: hosts, sign-in, invitations, platform operations, support sessions, tenant APIs, frontend.
  3. List the defects found during the phase and what fixed them.

## 1. Defects found and fixed during Phase 3

| Found in | Defect | Impact | Fix |
|---|---|---|---|
| M8 | A non-member can't sign in on a tenant host (D7), so an existing account could not accept an invitation at all | Functional gap; no exposure | Acceptance with the account's password: throttled, durable evidence, generic error (N80) |
| M9 E2E | Provisioning refused an empty `country` | Functional | Serializer allows blank; regression test (N89) |
| M10 | On a tenant host, institution and campus admins were reported as not requiring MFA | Users were not sent to enrolment. Privileged requests were still refused, so not a bypass | MFA requirement counts every scope of the tenant (N92) |
| M10 | Local tenant hosts failed CSRF origin checks (the port is missing from the forwarded host) | Dev and CI only | Documented trusted origin `http://*.localhost:8080` (N94) |
| M10 part 2 | The frontend rendered the platform sign-in page on unknown hosts | The API refused everything there, so no data was exposed; the page was misleading | Unknown-host detection, 404 (N97) |

## 2. Review of the attack surface

| Area | Checked | Result |
|---|---|---|
| Host resolution | Host from `Host` only; forwarded headers ignored; uniform 404; no lookup while disabled | OK (T5, T6) |
| Session binding | Sessions bound to their host; replayed cookies treated as anonymous without revoking the real session | OK |
| Sign-in on tenant hosts | Generic refusal for non-members, suspended memberships and suspended tenants (except owners, D2) | OK |
| Tenant API authorization | Permission class (any scope) + scope-filtered lists + exact-scope service checks; 404 for invisible objects; guard rails (escalation, last owner, self) | OK; the any-scope gate is never used on its own, every write re-checks in the service |
| Platform operations | Catalogued ids with uncached permission checks; registry fields only; both logs; completeness test | OK (T19, T20) |
| Invitations | Hashed token; fragment only; email binding; generic answers; throttles; password path throttled per invitation | OK. **Open hardening:** the inviter's permission is not re-checked at acceptance (recorded since M4) |
| Support sessions | Read-only; ≤ 2 h; tenant approval by default; per-request audit in the same transaction; revoked on suspension; nothing on suspended tenants | OK (T10) |
| Audit | Durable denial evidence; private dual-scope RLS; append-only grants | OK (T17) |
| Frontend | No tokens in storage; invitation token in the fragment only; branding colours validated before use; CSP unchanged; host-guarded routes | OK |
| Celery | Declared tasks only; tenant tasks with an explicit id; leak detectors; I/O guard | OK, except prefork K6 not run |

## 3. Residual risks and open items (for the owner)

1. **D9 isolation-overhead benchmark not measured.** Performance risk, not an isolation risk. Owner decision pending: before sign-off, or Phase 18.
2. **No Sentry alerting.** Isolation violations are logged and summarised daily, but nobody is paged. Needs a Sentry account (owner).
3. **Inviter re-check at acceptance** (above): an invitation outlives the inviter's permission until it expires (7 days) or is revoked.
4. **Tenant lists are filtered in Python** (institutions, campuses, invitations): correct, but not built for large tenants. Paginate before limits grow.
5. **Prefork K6** through the compose worker has not been run (threaded K6 passes).
6. **Production enablement (D1):** domain, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` (default HTTPS port: no extra entry), Nginx TLS for the wildcard, then this review approved. Only then set `TENANT_HOSTS_ENABLED=true`.

### Change notes
- 2026-11-21 — Created (Phase 3 M11).
