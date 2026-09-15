# Phase 14.31 — Customer account-menu and return-destination polish

## Purpose

Make successful customer login feel predictable and remove ambiguous account
controls from the app shell.

## What changed

- The signed-in email/role pill now opens an explicit account menu instead of
  navigating directly when clicked.
- The menu exposes clear actions: **My workspace** and **Sign out**.
- Generic customer sign-in requests now default to `/customer` when no protected
  destination is supplied or when the requested destination is the public home
  page.
- Customer logout now clears the short-lived route-auth cache in addition to
  forwarding the provider-backed logout flow.
- The customer session indicator refreshes when the current route changes so it
  is less likely to display stale signed-in state after navigation.

## Why this matters

The expected customer flow is now simpler:

1. Public landing page remains public.
2. Clicking **Sign in** opens customer authentication.
3. A successful sign-in opens **My Workspace** unless a specific protected route
   was requested.
4. Clicking the email/role control opens account actions rather than unexpectedly
   sending the user through protected-route validation.
5. Signing out removes both the durable customer session and the temporary route
   cache.

## Deliberate non-goals

This change does not alter WorkOS credentials, canary allowlists, user
provisioning, roles, entitlements, tenant-scoped data authorization, report
calculations, proximity metrics, collection requests, source-provider calls, PDP
calls, AI calls, PDFs, or historical artifacts.

