# Phase 13.49 — WorkOS administrator route-cache handoff

## Confirmed production behavior

After the Phase 13.48 route-proxy change deployed, production browser evidence still showed this loop:

1. `/customer` resolved `brian@cpghero.com` as `System owner`.
2. `/admin/login?return_to=%2Fadmin%2Fmatching-v2` called `/api/admin/session`.
3. `/api/admin/session` returned HTTP 200 quickly enough for the admin login page to enter its verified/redirecting state.
4. the next `/admin/matching-v2` navigation still returned HTTP 307 back to `/admin/login`.

This confirmed the remaining defect was not the customer identity, role grant, or top-right role label. The failing handoff was between the verified admin-session check and the protected `/admin/*` route boundary.

## Implemented change

`/api/admin/session` now issues a short-lived `cph_admin_route_auth` cookie only after `adminSessionStatus()` returns:

- `authenticated: true`; and
- `source: "customer_system"`.

The admin route cache is:

- HttpOnly;
- Secure in production;
- SameSite=Strict;
- path scoped to `/`;
- five minutes long; and
- cryptographically bound to the current `cph_customer_session` value.

The route proxy now accepts that admin route cache for `/admin/*` page shells and `/api/admin/*` route-boundary entry. The downstream admin API route handlers still run `verifyAdminAccess()` and remain the authoritative permission check for admin data and writes.

## Guardrails retained

- A customer route-auth cache cannot be replayed as an admin route-auth cache.
- `account_owner` alone still cannot create the admin route cache.
- Admin API handlers still verify the live CPGHero principal before returning protected data or accepting protected writes.
- Customer logout expires both the customer route cache and the admin route cache.
- No role grants, WorkOS credentials, canary allowlists, entitlements, report calculations, proximity metrics, source-provider calls, PDP calls, AI calls, PDFs, or historical artifacts changed.

## Verification

Focused tests cover:

- `/api/admin/session` sets the admin route cache only for verified WorkOS-backed system administrators.
- non-system customers and legacy admin sessions do not receive a customer-system admin route cache.
- the proxy allows admin page shells when the admin route cache matches the current customer session.
- the proxy rejects a customer route-cache token presented as admin route access.
- logout clears the admin route cache.
