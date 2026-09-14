# Phase 13.105 — Customer Auth Cookie Bridge Hotfix

## Summary

Customer AuthKit callbacks can return more than one `Set-Cookie` header: one cookie seals the CPGHero customer session and another clears the temporary login-flow cookie. The same-origin web proxy now preserves each cookie separately even when the runtime presents them as a combined header value.

## Why it matters

The customer login flow is only trustworthy if a successful identity-provider callback creates a usable CPGHero session exactly once. If callback cookies are collapsed into an invalid browser header, the app can authenticate successfully upstream and then immediately redirect back to login, producing a customer-visible redirect loop.

## Behavior

- `/api/auth/callback` still runs through the internal API and remains same-origin to the browser.
- The web proxy forwards callback redirect locations and every upstream `Set-Cookie` value independently.
- Combined cookie headers are split only on cookie-boundary commas, preserving comma-containing attributes such as `Expires`.
- The customer session cookie remains HttpOnly and is the value validated by protected customer routes.
- The temporary customer-auth flow cookie is still cleared after callback completion.

## Verification

- Added regression coverage for a callback response containing both `cph_customer_session` and `cph_customer_auth_flow` cookie mutations.
- Ran `pnpm --filter @rci/web test -- src/lib/customer-auth-proxy.test.ts`.
- Ran `pnpm --filter @rci/web typecheck`.

## Non-goals

This does not broaden the canary allowlist, change WorkOS application settings, expose provider credentials, bypass CPGHero account/workspace authorization, grant report entitlements, or alter downstream analytics/reporting access controls.
