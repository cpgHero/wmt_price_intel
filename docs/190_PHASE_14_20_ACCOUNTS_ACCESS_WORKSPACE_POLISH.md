# Phase 14.20 — Accounts & Access workspace polish

Date: 2026-09-14
Status: local verification in progress

## Outcome

The internal account administration surface is now presented as Accounts &
Access instead of Customer Auth. The page keeps the existing protected route but
organizes the operator experience around customer accounts, workspaces, users,
roles, entitlements, report-grant counts, and a secondary login-readiness view.

## Changes

- Rename the visible administration navigation and page header to Accounts &
  Access.
- Default the account workspace to customer accounts only, with an explicit
  option to include system/internal account records.
- Replace the account-slug-only filter with account, slug, and user-email
  search.
- Add an overview account selector and detail panel for workspaces, users,
  roles, entitlements, identity binding, and report-grant counts.
- Add clear empty states when a filtered view has no accounts, workspaces,
  users, entitlements, invitations, or identity events.
- Move customer-login readiness into a dedicated workspace tab so it no longer
  dominates the account administration experience.
- Remove visible upstream identity-provider naming from current page copy while
  keeping backend adapter contracts and historical docs intact.

## Non-goals

This phase does not add writable account administration, customer self-service
settings, API key issuance, billing, identity-provider migration, report
calculation changes, matching changes, price normalization changes, proximity
metric changes, source-provider calls, PDP calls, AI calls, PDFs, or historical
artifact changes.

## Verification plan

- Source-contract tests protect the read-only account foundation, visible
  Accounts & Access naming, customer-only default filter, reset flow, account
  detail workspace, and visible identity-provider masking.
- Navigation tests keep the existing protected route stable.
- Standard release gates should run web tests, lint, typecheck, build, GitHub
  Actions, deployment, and production smoke checks.
