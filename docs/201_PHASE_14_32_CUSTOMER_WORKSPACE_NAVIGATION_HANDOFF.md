# Phase 14.32 — Customer workspace navigation handoff

## Purpose

Remove the remaining ambiguity from the signed-in account menu's **My workspace**
action.

## What changed

- The **My workspace** action now performs an explicit same-origin
  `/api/auth/me` check immediately before navigating.
- A successful check primes the customer route-auth cache and then performs a
  full browser navigation to `/customer`.
- A failed check sends the browser through customer login with
  `return_to=/customer`.
- The action shows an **Opening workspace…** state while the handoff is in
  progress.

## Why this matters

The account menu can show a signed-in customer because `/api/auth/me` resolves
successfully from the browser. The **My workspace** action should rely on that
same source of truth before navigating, rather than letting a client-side route
transition or prefetch path decide independently.

## Deliberate non-goals

This change does not alter WorkOS credentials, canary allowlists, user
provisioning, roles, entitlements, tenant-scoped data authorization, report
calculations, proximity metrics, collection requests, source-provider calls, PDP
calls, AI calls, PDFs, or historical artifacts.

