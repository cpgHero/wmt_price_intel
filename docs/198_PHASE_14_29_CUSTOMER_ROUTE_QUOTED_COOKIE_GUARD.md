# Phase 14.29 Customer route quoted-cookie guard

## Scope

Customer route-boundary hardening for the production customer-login canary.

## Change

The Next.js route boundary now reads customer-auth cookies through a normalized helper:

- uses the framework cookie parser when available;
- falls back to the raw `Cookie` header;
- strips surrounding quotes from sealed cookie values before route-cache comparison.

This applies to both the `cph_customer_session` cookie and the short-lived customer route-validation cache cookie.

## Rationale

After the callback completion guard shipped, production logs showed a more precise failure pattern:

- successful `/api/auth/callback` responses returned `200`;
- the completion page validated the customer session through `/api/v1/me` with `200`;
- the browser was still sent back to `/api/auth/login?return_to=/customer`.

That means the CPGHero API could read and validate the sealed session, but the web route boundary could still miss the same cookie before allowing the protected `/customer` route. Sealed session cookies can be quoted when set through standard response-cookie serialization, so the route boundary must not depend on one framework parser path only.

## Verification

- `apps/web/src/proxy.test.ts` verifies that a quoted sealed customer-session cookie with padding is recognized at the route boundary and accepted with a valid route-cache cookie without re-entering hosted login.

## Explicit non-goals

This does not change WorkOS credentials, WorkOS user provisioning, canary allowlists, roles, entitlements, account/workspace authorization, report calculations, proximity metrics, collection requests, source-provider calls, PDP calls, AI calls, PDFs, or historical artifacts.
