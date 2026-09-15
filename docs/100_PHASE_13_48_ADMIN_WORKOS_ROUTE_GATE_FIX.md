# Phase 13.48 — WorkOS-backed admin route gate fix

## Confirmed defect

Production browser evidence showed the administrator login page could verify a WorkOS-backed CPGHero user through `/api/admin/session`, display the “Checking CPGHero administration access” card, and redirect to the requested `/admin/*` page. The route proxy then immediately redirected the request back to `/admin/login`, causing a visible flash loop.

The confirmed code cause was a route-boundary mismatch:

- `/api/admin/session` accepted either the legacy administrator session or a resolved CPGHero customer principal whose permissions include `system.admin`.
- The route proxy still checked only the legacy administrator cookie before allowing `/admin/*` page shells and `/api/admin/*` routes.

## Implemented change

The route proxy now validates administrator access when either of these cookies is present:

- the legacy administrator cookie; or
- the customer session cookie, validated through `/api/admin/session`.

For WorkOS-backed customer sessions, the proxy does not trust the cookie directly. It forwards the request cookies to `/api/admin/session` and only allows the admin route when that endpoint returns `authenticated: true`.

The customer identity pill now uses a shared, tested role-label priority so a principal with both `account_owner` and `system_owner` displays `System owner` in the top navigation, matching the role state shown inside My Workspace.

## Guardrails retained

- `account_owner` alone does not unlock internal Administration.
- Admin API routes still return private JSON `401` responses when unauthorized.
- Admin page routes still redirect to `/admin/login` when unauthorized.
- Customer route-auth caching remains limited to customer routes; it does not become an admin authorization cache.
- No WorkOS credentials, canary allowlists, roles, entitlements, report calculations, proximity metrics, source-provider calls, PDP calls, AI calls, PDFs, or historical artifacts changed.
- The identity-pill change is presentation only; it does not add or remove permissions.

## Verification

Focused web tests were updated to cover:

- WorkOS-backed customer sessions with `system.admin` can reach `/admin/*` page shells.
- WorkOS-backed customer sessions with `system.admin` can reach `/api/admin/*` routes.
- customer sessions without `system.admin` still redirect from `/admin/*` page shells.
- customer sessions without `system.admin` still receive admin JSON `401` from `/api/admin/*`.
- the customer identity pill prioritizes `system_owner` over `account_owner` when both roles are present.

Local focused verification passed:

```text
Test Files  43 passed
Tests       251 passed
```
