# Phase 13.106 — Customer Auth Background Request Guard

## Summary

Protected customer pages and the customer login endpoint now prevent background React Server Component and prefetch requests from launching the external hosted login flow.

## Why it matters

Customer authentication must be initiated by a deliberate browser navigation such as clicking Sign in or opening a protected page. Background page-data requests can happen several times in parallel while the app shell is loading. If those requests are redirected into hosted login, a browser with an existing identity session can repeatedly bounce through callback and login URLs, creating a customer-visible redirect loop.

## Behavior

- Top-level customer page navigations still redirect to `/api/auth/login`.
- Normal `/api/auth/login` browser navigations still start hosted login.
- Requests carrying `_rsc`, `RSC: 1`, `Next-Router-Prefetch: 1`, `Purpose: prefetch`, or `Sec-Purpose: prefetch` fail closed with private no-store `401` responses instead of creating a new login session.
- Requests that do not present as HTML document navigations also fail closed. This prevents production framework traffic whose internal RSC markers are normalized or stripped before application code from starting hosted login.
- Protected API routes continue to return private no-store JSON `401` responses when unauthenticated.
- The customer route-boundary cache and authoritative API permission checks remain unchanged.

## Verification

- Added middleware regression coverage proving unauthenticated RSC requests do not redirect to hosted login.
- Added login-route regression coverage proving `/api/auth/login?_rsc=...` cannot start hosted login.

## Non-goals

This does not change WorkOS application configuration, broaden the customer-auth canary allowlist, alter account/workspace provisioning, grant entitlements, expose provider credentials, or weaken downstream API authorization.
