# Phase 13.56 — WorkOS administrator principal proxy alignment

## Confirmed production behavior

After the admin route-cache handoff deployed, production still showed an administrator loop:

1. `/customer` resolved `brian@cpghero.com` as a CPGHero `System owner`.
2. My Workspace displayed the `system.admin` permission in the resolved permission list.
3. Production Railway variables required for WorkOS customer auth and route-cache signing were present.
4. `/admin/matching-v2` still redirected to `/admin/login?return_to=%2Fadmin%2Fmatching-v2`.
5. During the loop, `/api/admin/session` returned HTTP 200 with the same small unauthenticated response size seen for anonymous checks, while `/api/auth/me` returned the populated signed-in customer response.

That evidence narrowed the remaining issue to the administrator customer-principal resolver path, not the production role grant, the visible customer session, or missing Railway secrets.

## Implemented change

Administrator access now resolves WorkOS-backed CPGHero customer principals through the same customer-auth proxy path used by `/api/auth/me`.

Specifically:

- `adminSessionStatus()` still accepts the existing legacy administrator password session first.
- if there is no valid legacy admin session, it calls the shared customer-auth proxy path for `/api/v1/me`;
- it parses the returned CPGHero principal and requires the canonical `system.admin` permission;
- `account_owner` without `system.admin` remains blocked; and
- `/api/admin/session` is explicitly `force-dynamic` and only issues the separate `cph_admin_route_auth` cache after `customer_system` authentication.

## Guardrails retained

- WorkOS credentials, provider keys, and session cookie values are never exposed in the browser or docs.
- CPGHero remains the authorization source of truth for accounts, workspaces, roles, permissions, entitlements, and admin access.
- Every protected `/api/admin/*` route handler continues to run `verifyAdminAccess()` before returning protected data or accepting protected writes.
- Customer route-cache tokens and administrator route-cache tokens remain separate scopes.
- No role grants, canary allowlists, report calculations, proximity metrics, product Search evidence, observed product distribution, matching, source-provider calls, PDP calls, AI calls, PDFs, or historical artifacts changed.

## Verification

Focused web auth regression tests cover:

- legacy administrator sessions remain accepted without customer-principal lookup;
- WorkOS-backed customer principals with `system.admin` are accepted;
- account owners without `system.admin` are rejected;
- the administrator customer-principal lookup forwards the same customer session and forwarded request context used by the working customer-auth proxy path;
- `/api/admin/session` still creates the admin route cache only for `customer_system`; and
- proxy route-cache replay protections remain intact.
