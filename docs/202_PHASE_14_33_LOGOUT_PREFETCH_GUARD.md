# Phase 14.33 — Logout prefetch guard

## Purpose

Prevent customer sessions from being destroyed by framework background requests.

## Finding

Production logs showed successful customer session checks followed immediately by
requests such as:

```text
GET /api/auth/logout?_rsc=...
```

Those requests were caused by rendering logout as a Next.js `Link`. The framework
can prefetch visible links in the app shell; because logout was a state-changing
GET endpoint, that background request could clear the customer session before the
user intentionally clicked **Sign out**.

## What changed

- `/api/auth/logout` now rejects RSC, prefetch, non-document, and other
  background requests without forwarding them to the API.
- Logout controls are rendered as ordinary anchors instead of Next.js `Link`
  components so they are not framework-prefetched.
- The intentional browser logout flow still clears the customer session and the
  short-lived route-auth cache.

## Deliberate non-goals

This change does not alter WorkOS credentials, canary allowlists, user
provisioning, roles, entitlements, tenant-scoped data authorization, report
calculations, proximity metrics, collection requests, source-provider calls, PDP
calls, AI calls, PDFs, or historical artifacts.

