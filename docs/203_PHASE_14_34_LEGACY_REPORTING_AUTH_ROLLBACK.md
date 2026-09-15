# Phase 14.34 — Legacy reporting and customer-auth rollback

## Purpose

Stop the customer identity rollout, remove the WorkOS/customer-route login loops
from the active app experience, and restore the legacy pricing and competitive
intelligence reporting path while keeping Proximity available.

## What changed

- The Next.js proxy no longer validates WorkOS, customer-session, route-cache, or
  administrator-session cookies at the route boundary.
- Dormant customer pages redirect to legacy destinations: `/customer` goes to
  `/`, and customer report detail URLs go to `/analyses`.
- Customer auth endpoints are disabled or redirected: login, callback, and
  logout send users back to the root app; `/api/auth/me` returns a private
  no-store 401 response.
- Customer report APIs return a private no-store disabled response instead of
  proxying or serving the newer customer/canonical report experience.
- Administration authorization is restored to the legacy password session through
  `/api/admin/session` and downstream `verifyAdminAccess` checks.
- The app shell no longer renders the customer account menu, the root route
  renders the legacy operational home/dashboard, normal navigation is restored,
  and `/analyses/[analysisId]` renders the legacy Blueprint Competitive
  Intelligence workspace.
- Proximity remains active and retains its current implementation.

## Verification

- `pnpm format:check`
- `pnpm --filter @rci/web test`
- `pnpm --filter @rci/web typecheck`
- `pnpm --filter @rci/web lint`
- `pnpm --filter @rci/web build`
- Built-server HTTP probes confirmed:
  - `/`, `/analyses`, `/proximity`, and `/admin/login` return 200.
  - `/customer` redirects to `/`.
  - `/customer/reports/test-access` redirects to `/analyses`.
  - `/api/auth/me` returns 401 with `cache-control: private, no-store`.
  - `/api/auth/login`, `/api/auth/callback`, and `/api/auth/logout` redirect to
    `/`.
  - `/api/customer/reports` and customer report detail API paths return 404 with
    `cache-control: private, no-store`.
  - `/api/webhooks/workos` acknowledges with 204 and `cache-control: private,
    no-store`.

## Deliberate non-goals

This is a code-level rollback only. It does not delete WorkOS configuration,
drop account/RBAC database tables, remove Railway secrets, mutate raw evidence,
change location rows, alter retailer eligibility, change observed product
distribution, update matching decisions, recalculate reports, make
source-provider calls, make PDP calls, make AI calls, regenerate PDFs, or modify
historical artifacts.
