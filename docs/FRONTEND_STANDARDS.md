# Frontend Standards

> Next.js 16 (App Router), TypeScript (strict), Tailwind CSS, shadcn/ui. Mobile-first, accessible, multi-language, tenant-themed.

## 1. Application structure (proposed)

```
frontend/
  src/
    app/
      [locale]/
        (auth)/login, forgot-password, invite/[token]
        (tenant)/                     tenant app shell (sidebar/topbar, entitlement-driven nav)
          dashboard/
          students/  attendance/  exams/  fees/  hostel/ ...   (one route group per module)
          settings/  studio/          Customization Studio
        (portal)/                     guardian/student portal (simplified mobile-first shell)
        (public)/apply/[cycle]        public admission forms
        (platform)/                   Super Admin console (platform domain only)
    components/
      ui/                             shadcn/ui generated components (owned source)
      common/                         shared composites (DataTable, PageHeader, EmptyState, MoneyText, DateText…)
    features/<module>/                module-specific components, hooks, schemas
    lib/
      api/                            generated client wrapper (from packages/api-client), query keys
      auth/  i18n/  permissions/  tenant/  utils/
    messages/                         en.json, bn.json, ar.json
    styles/
  tests/  (vitest)   e2e/ (playwright)
```

## 2. Rendering & data

- **Server Components by default**; `"use client"` only for interactivity (forms, tables with client state, charts).
- Data fetching: server-side via typed API client for initial render where useful; **TanStack Query** for client-side server state (caching, mutations, optimistic updates where safe — never optimistic for money).
- Never duplicate backend types by hand — import from the generated client.
- Mutations invalidate precise query keys (`['students', tenantId, filters]`).
- Errors: map Problem Details `code` to user-friendly localized messages; show `request_id` in error details for support.
- Long jobs: poll job endpoint or SSE (ADR-022), show progress.

## 3. Auth & tenant context

- **Session auth (ADR-011):** login/logout/MFA forms post directly to the Django API on the same origin (`/api/v1/auth/...`).
  - Django sets the HttpOnly session cookie. The frontend never reads, stores or forwards tokens in client code, and there are no token-exchange route handlers.
  - Client-side requests use `credentials: 'include'` and send `X-CSRFToken` on unsafe methods.
  - Server components call the API on the internal network, forwarding the incoming `Cookie` header and the original `Host`/`X-Forwarded-Host` so tenant resolution still works.
- `middleware.ts` (or Next.js 16 equivalent `proxy`) resolves locale and redirects unauthenticated users; it does **not** make security decisions — the API does.
- Tenant branding/config/entitlements/permissions loaded once per session from `/api/v1/me/context/` and provided via context; refreshed on change.

## 4. Entitlement & permission-driven UI

- Navigation and actions render from the server-provided manifest: entitled modules + user permissions + terminology.
- Helpers: `<Can permission="fees.payment.collect">…</Can>`, `useCan()`, `<ModuleGate module="hostel">`.
- **Hiding is UX only**; the server enforces. Never rely on hidden buttons for security.
- Terminology overrides (e.g. "Section" → "Jamaat") come from resolved config into i18n messages; components use `t('academics.unit.section')`, never hardcoded labels.

## 5. Forms

- react-hook-form + zod; zod schemas derived from/aligned with OpenAPI types; server validation errors mapped to fields.
- Dynamic forms (Studio forms, custom fields) rendered by a single `DynamicForm` renderer from definitions — no per-tenant components.
- Money inputs use decimal strings; never JS floating-point arithmetic for money (use a decimal library if client-side computation is needed; server is authoritative).
- Payment/money submissions send an `Idempotency-Key` (generated per submit intent) and disable double-submit.

## 6. Design system

- shadcn/ui + Tailwind; design tokens as CSS variables (`--primary`, `--radius`, …) so tenant branding (primary color, logo) applies without code changes; contrast checked automatically when tenants pick colors (fallback to accessible color).
- Light and dark themes.
- Typography: fonts supporting Latin, **Bengali** and **Arabic** scripts (e.g. a Bengali-capable font such as Noto Sans Bengali / Hind Siliguri and Noto Naskh/Kufi Arabic — final choice in Phase 1/5); `font-display: swap`; self-hosted via `next/font`.
- Spacing/layout: 4 px grid, consistent page templates (list page, detail page, form page, dashboard).
- Icons: lucide-react.

## 7. Mobile-first & performance

- Design at 360 px first; core teacher/guardian/student flows (attendance marking, marks entry, fee payment, results) must be fully usable one-handed on mobile.
- Tables become cards/stacked lists on small screens; sticky primary actions.
- Performance budgets (proposed): LCP < 2.5 s on mid-range Android over 4G, JS per route kept small; image optimization via `next/image`; route-level code splitting; avoid heavy client libraries.
- PWA capabilities (installable, offline-tolerant attendance capture with later sync) are a **proposed** later enhancement — requires conflict-resolution design before adoption.

## 8. Internationalization

- `next-intl`; locales: `en`, `bn` initially; `ar` (RTL) ready. Tenant chooses enabled locales; users choose their locale.
- Use logical CSS properties (`ms-*`, `me-*`, `start`/`end`) to support RTL.
- Numbers, dates, currency formatted with `Intl` per locale (Bengali digits optional per tenant setting).
- Calendar display: Gregorian default; Hijri display support proposed for madrasa tenants (verify library support before committing).
- No string literals in components for user-facing text (lint rule).

## 9. Accessibility (WCAG 2.2 AA target)

- Semantic HTML, labelled inputs, focus management in dialogs (Radix), keyboard navigation, visible focus, color contrast ≥ 4.5:1, `aria-live` for async status, no information by color alone.
- Automated checks: `eslint-plugin-jsx-a11y`, axe in Playwright for key pages.

## 10. Code quality

- TypeScript `strict`, `noUncheckedIndexedAccess`; no `any` without `// reason:` comment.
- ESLint (flat config, Next.js + TypeScript + a11y + import rules) + Prettier; `tsc --noEmit` in CI.
- Components: small, typed props, no business logic duplication from backend (server computes totals, grades, balances).
- Tests: Vitest + Testing Library for components/hooks; Playwright for E2E critical flows (login, attendance, marks entry, fee payment, studio publish).
- Security: no `dangerouslySetInnerHTML` except sanitized (DOMPurify) rich text; no tokens in localStorage; CSP-compatible (no inline scripts without nonce).

### Change notes
- 2026-11-05 — Initial version (Phase 0).
- 2026-11-05 — Updated for owner-approved ADR-009/010/011/012/013/014 (session auth, transaction-scoped RLS context, DB roles, UUIDv7 abstraction, tenant-level subscription with campus limits, uv/pnpm, layout).
