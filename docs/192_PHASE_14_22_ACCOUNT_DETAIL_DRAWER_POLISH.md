# Phase 14.22 — Account detail drawer polish

Date: 2026-09-14
Status: local verification in progress

## Outcome

The Accounts & Access workspace now has a richer read-only account detail
drawer. Operators can inspect one customer account without leaving the account
directory context, and the detail view now groups the most important access
evidence into decision-oriented sections.

## Changes

- Open a full-height account detail drawer from account cards and account table
  rows.
- Add drawer summary cards for workspace count, active users, report grants, and
  login readiness.
- Add a login, invitation, and identity readiness section for the selected
  account.
- Add workspace/report-access, users/roles, and entitlements sections with clear
  empty states.
- Preserve a visible read-only guardrail explaining that membership, role,
  entitlement, and report-access mutations require explicit approval, audit, and
  rollback workflows before they are enabled.

## Non-goals

This phase does not add writable account administration, invitations,
re-invitations, role edits, entitlement edits, report-grant edits, API key
issuance, billing, customer self-service settings, customer-login cutover,
identity-provider migration, reports, proximity metrics, collection requests,
source-provider calls, PDP calls, AI calls, PDFs, or historical artifacts.

## Verification plan

- Source-contract tests protect the account detail drawer, readiness section,
  report-access section, and read-only guardrail language.
- Web lint, typecheck, build, and focused source tests.
- Full CI before merge and production smoke after deployment.
