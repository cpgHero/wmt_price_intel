# Phase 14.25 — Customer Route Auth Validation Cache

Date: 2026-09-14

Status: Local verification complete; PR verification pending.

## Summary

The Next.js route boundary now avoids repeated customer session validation bursts during protected app navigation. After a customer session validates successfully through the existing same-origin customer auth endpoint, the web app sets a short-lived CPGHero-signed route-validation cache cookie.

The cache is bound to the current customer session cookie and expires quickly. Missing, malformed, expired, tampered, or cross-session cache values fail closed to the existing validation path.

## Operational effect

- Protected customer pages and same-origin app API proxy routes still require a valid customer session before the page shell or app API proxy runs.
- Rapid page, RSC, and app API request bursts can reuse the local route-validation cache instead of repeatedly calling the customer session validator.
- API handlers remain the authoritative enforcement layer for permissions, entitlements, account/workspace scope, report grants, and tenant-specific data access.
- Administrator route validation continues to use the existing administrator session endpoint.

## Compatibility and boundaries

This change only reduces customer route-boundary validation frequency. It does not change customer provisioning, WorkOS credentials, roles, entitlements, report calculations, proximity metrics, collection requests, source-provider calls, PDP calls, AI calls, PDFs, or historical artifacts.

The route-validation cache is not an authorization decision and is not a substitute for tenant-scoped API authorization.

## Verification

- `corepack pnpm --filter @rci/web test -- proxy route-auth-cache route-access-policy platform-docs customer-auth-config customer-auth-proxy`
- `corepack pnpm format:check`
- `corepack pnpm --filter @rci/web lint`
- `corepack pnpm --filter @rci/web typecheck`
- `corepack pnpm --filter @rci/web build`
- `python3 scripts/check_platform_docs_coverage.py --base-ref origin/main`
- `git diff --check`
- Local production smoke verified:
  - `/` redirects to customer login.
  - `/proximity` redirects to customer login.
  - `/api/proximity/retailers?country=USA` returns JSON 401.
  - A fake customer session cookie still fails closed.
  - `/health` remains public.
