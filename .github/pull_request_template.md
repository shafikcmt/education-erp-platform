## Summary
<!-- What does this change and why? -->

## Phase
<!-- e.g. Phase 1 — Repository foundation & infrastructure -->

## Affected modules
<!-- module codes from CLAUDE.md §5 -->

## Migrations
<!-- None / list migrations; locking impact; RLS policy for new tenant tables -->

## Security implications
- [ ] Tenant isolation preserved (tenant-scoped models, selectors, isolation tests)
- [ ] Permissions enforced server-side (allowed + denied tests)
- [ ] Module entitlement enforced
- [ ] Input validated; no raw SQL (or reviewed)
- [ ] Financial ops atomic, idempotent, audited (if applicable)
- [ ] No secrets / PII in code, logs, tests, fixtures
- [ ] New dependencies justified and scanned

## Tests run (with results)
<!-- exact commands and pass/fail counts -->

## Docs updated
<!-- DEVELOPMENT_PROGRESS.md, DECISION_LOG.md, others -->
