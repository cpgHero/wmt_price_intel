# Phase 14.30 — Customer auth route-cache priming

## Purpose

Remove the remaining brittle edge in the WorkOS/AuthKit callback handoff where the
first-party callback page could validate `/api/auth/me`, but the next protected
route navigation could still be sent back to hosted login.

## What changed

- `/api/auth/me` now primes the short-lived CPGHero customer route-auth cache
  after the upstream API successfully validates the customer session.
- The cache is signed by CPGHero, bound to the exact customer session cookie, and
  remains valid only for the existing short route-cache window.
- The protected route boundary and the `/api/auth/me` route share the same cookie
  normalization path, including quoted sealed cookie values.
- The callback completion page now times out its `/api/auth/me` verification
  request after eight seconds and shows the controlled manual recovery state
  instead of hanging indefinitely.

## Why this matters

The successful callback sequence now has one deterministic same-origin handoff:

1. WorkOS/AuthKit returns to CPGHero.
2. CPGHero API sets the HttpOnly customer session cookie on the completion page.
3. The completion page calls `/api/auth/me`.
4. `/api/auth/me` validates the session with the API and sets the route cache.
5. The browser navigates to the protected customer app route.

That means a valid signed-in browser should not bounce back into hosted login just
because the route shell is handling the first protected navigation immediately
after callback completion.

## Deliberate non-goals

This change does not alter WorkOS credentials, canary allowlists, user
provisioning, roles, entitlements, tenant-scoped data authorization, report
calculations, proximity metrics, collection requests, source-provider calls, PDP
calls, AI calls, PDFs, or historical artifacts.

## Verification

- Added a web route test proving `/api/auth/me` sets a valid route-auth cache for
  a quoted sealed customer session cookie after a successful upstream `/api/v1/me`
  response.
- Added a web route test proving `/api/auth/me` does not set the route-auth cache
  when upstream customer session validation fails.
- Added API coverage confirming the callback completion page contains the
  bounded verification timeout.

