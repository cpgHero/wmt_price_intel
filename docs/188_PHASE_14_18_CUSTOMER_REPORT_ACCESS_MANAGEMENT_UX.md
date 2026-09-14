# Phase 14.18 — Customer report access management UX

Date: 2026-09-14
Status: local verification in progress

## Purpose

Make the internal customer report access workflow easier and safer to operate
now that customer report pages are backed by explicit grant IDs.

## Changes

- Add access overview cards for active grants, represented accounts,
  workspace/account-level scopes, and ready reports eligible for granting.
- Add account and workspace scope rollups so operators can quickly see where
  customer report access currently exists.
- Add ready-report search before granting to reduce selection mistakes when the
  ready report list grows.
- Add grant ledger search plus active, revoked, and all filters.
- Add direct customer-view links for active grants.
- Require a two-step soft-revoke action in the UI; the backend still updates the
  grant status and preserves the audit row.

## Non-goals

This phase does not add customer self-service administration, broaden account or
workspace roles, change WorkOS authentication, expose source-provider
credentials, issue customer API keys, change billing, alter report calculations,
matching, price normalization, source evidence, PDFs, proximity metrics,
collection requests, PDP calls, AI calls, or historical artifacts.

## Verification plan

- Source-contract test for the customer report access management controls.
- Web lint, typecheck, and build.
- CI before merge.
- Production smoke after Railway deploy.
