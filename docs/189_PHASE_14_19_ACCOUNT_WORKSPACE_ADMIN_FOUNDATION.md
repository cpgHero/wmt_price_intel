# Phase 14.19 — Account/workspace administration foundation

Date: 2026-09-14

## Outcome

The internal Customer Auth administration page now includes a source-backed,
read-only account/workspace foundation view. This gives CPGHero operators one
place to inspect customer account structure before any broader self-service
administration workflow is introduced.

## Source of truth

The new snapshot is computed server-side from existing platform tables:

- `account`
- `workspace`
- `account_membership`
- `workspace_membership`
- `platform_role` and membership role junctions
- `account_entitlement`
- `external_identity`
- `customer_account_invitation`
- `customer_report_access`

The response intentionally exposes identity-provider binding booleans rather
than upstream subject identifiers. Customer-facing and operator-facing UI remains
CPGHero-branded.

## What administrators can see

- Account inventory with status, account type, workspace count, member count,
  entitlement count, active report grants, revoked report grants, and whether an
  organization identity binding exists.
- Workspace scopes with active members and report grants.
- Members with account/workspace membership status, account/workspace role keys,
  and whether a user identity binding exists.
- Entitlements with account, entitlement key, status, and start/expiration
  timestamps when present.

## Non-goals

This phase does not add customer self-service administration, writable role
management, writable entitlement management, API key issuance, billing workflows,
collection-project authorization, report calculation changes, proximity metric
changes, matching changes, source-provider calls, PDP calls, AI calls, PDFs, or
historical artifact changes.

## Verification plan

- API contract test proves the new account-foundation endpoint is admin guarded
  and does not expose upstream identity-provider subject IDs.
- Web source-contract test protects the read-only account foundation sections and
  upstream masking language.
- Standard release gates should run API tests, web tests, lint/typecheck/build,
  GitHub Actions, deployment, and production smoke checks.
