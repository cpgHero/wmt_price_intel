# Phase 14.23 — Protected route authentication boundary

## Objective

Stop anonymous users from viewing protected CPGHero page shells while preserving
the existing API-level authentication and authorization controls.

## Implemented

- Added a shared web route-access policy for public, customer-protected, and
  administrator-protected paths.
- Added a Next.js `proxy.ts` route boundary:
  - anonymous app workspace, analytics, customer workspace, and customer report
    pages redirect to customer login with the original return path;
  - anonymous administrator pages redirect to `/admin/login` with the original
    return path;
  - protected same-origin app/admin API routes return private no-store JSON 401
    responses when the expected session is absent or invalid;
  - public auth, admin-session, WorkOS webhook, health, and static asset routes
    remain reachable.
- Added a dedicated administrator login page so `/admin/*` pages can be blocked
  before their page shells render.
- Added route-policy regression tests for the protected/public boundary.
- Added an explicit Playwright-only route-auth bypass token/header so existing
  UI regression tests can continue to exercise mocked protected pages. Production
  must not configure `CPGHERO_WEB_ROUTE_AUTH_TEST_BYPASS_TOKEN`.

## Security boundary

The route boundary validates the expected customer or administrator cookie
through the existing same-origin auth/session endpoints before protected pages
or protected same-origin app/admin API proxies run. It prevents anonymous,
expired, or forged cookies from opening protected page shells. It is still not
the source of truth for authorization.

The authoritative controls remain in API and service routes:

- customer session validation;
- role, permission, and entitlement checks;
- account and workspace scope checks;
- customer report grant checks;
- administrator session validation for internal admin APIs.

Invalid, expired, forged, or out-of-scope sessions still fail closed when data
routes are called.

The Playwright bypass is for test harnesses only. It requires both
`CPGHERO_WEB_ROUTE_AUTH_TEST_BYPASS_TOKEN` on the web server and a matching
`x-cpghero-route-auth-test` request header.

## Not changed

- No WorkOS credentials changed.
- No account, workspace, role, entitlement, invitation, or report-grant rows
  changed.
- No report calculations, proximity metrics, collection requests, source
  provider calls, PDP calls, AI calls, PDFs, or historical artifacts changed.
- No tenant-scoped conversion of legacy collection, global analysis, or
  proximity APIs was completed in this phase.

## Follow-up

Convert remaining legacy read routes to customer-scoped API contracts before
exposing them as customer-facing features. Proximity should eventually load from
a customer-authorized project/geography/comp-group context, not from global
location endpoints.
