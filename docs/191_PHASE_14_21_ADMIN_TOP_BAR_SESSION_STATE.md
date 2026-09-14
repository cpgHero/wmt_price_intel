# Phase 14.21 — Admin top-bar session state

Date: 2026-09-14
Status: local verification in progress

## Outcome

Admin workspaces no longer show the customer-login "Sign in" link in the app
top bar when the current browser has no customer session. The top bar instead
shows "Admin protected" so operators understand that access is governed by the
administrator session challenge inside the page.

## Changes

- Detect `/admin` routes in the customer account menu.
- Preserve normal customer sign-in behavior outside administrator workspaces.
- Display an informational admin-session indicator on administrator routes when
  no customer session exists.

## Non-goals

This phase does not change customer login, administrator authentication,
identity-provider configuration, roles, entitlements, account data, report
access, reports, proximity metrics, collection requests, source-provider calls,
PDP calls, AI calls, PDFs, or historical artifacts.

## Verification plan

- Web lint and TypeScript typecheck.
- Git diff whitespace check.
- Full CI before merge and production smoke after deployment.
