# Phase 14.27 Customer auth callback completion page

## Scope

Customer AuthKit callback hardening for the production customer-login canary.

## Change

Successful `/api/auth/callback` responses now set the CPGHero customer-session cookie on a first-party CPGHero HTML completion page instead of immediately issuing a second server-side redirect to the protected return path.

The completion page is private/no-store, CPGHero-branded, and immediately navigates to the validated return path with `window.location.replace`, with a meta-refresh and link fallback.

## Rationale

Google social login through hosted AuthKit produced repeated successful WorkOS authorization-code exchanges followed by immediate customer-login restarts. The API log pattern showed:

- WorkOS `/user_management/authenticate` returned `200 OK`.
- CPGHero `/api/auth/callback` returned a successful `303`.
- The browser then immediately hit `/api/auth/login?return_to=/customer` again, with no intervening customer-session validation.

That pattern indicates the new CPGHero session cookie was not available to the protected route boundary on the immediate post-callback redirect. Returning a first-party completion document gives the browser a stable CPGHero response on which to commit the session cookie before the same-origin navigation into protected app routes.

## Verification

- `apps/api/tests/test_customer_identity.py` verifies the callback completion page:
  - returns `200`
  - remains `private, no-store`
  - sets the CPGHero customer-session cookie
  - clears the temporary login-flow cookie
  - navigates to the safe return path

## Explicit non-goals

This does not change WorkOS credentials, WorkOS user provisioning, canary allowlists, roles, entitlements, account/workspace authorization, report calculations, proximity metrics, collection requests, source-provider calls, PDP calls, AI calls, PDFs, or historical artifacts.
