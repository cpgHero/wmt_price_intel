# Phase 14.09 — WorkOS webhook event hardening

Date: 2026-09-14

## Purpose

Repair production WorkOS identity webhook processing after the first customer invitation flow
surfaced a server-side event-processing failure.

## Triggering evidence

- WorkOS delivered a signed `user.created` event for an invited customer user.
- Signature verification reached the API successfully.
- The API then returned HTTP 500 because the invitation lookup query used nullable text parameters
  without explicit casts, which PostgreSQL could not type-plan in the production driver path.
- The incoming `user.created` payload stores the WorkOS user subject in `data.id`; the receiver
  previously treated `data.id` as a possible invitation id for all event types.

## Implemented scope

- Cast nullable `workos_invitation_id` and `email` lookup parameters as text before `IS NOT NULL`
  checks and equality comparisons.
- Extract WorkOS user ids and invitation ids by event type so `user.created` and `user.updated`
  bind `data.id` as a user subject, while invitation events keep invitation ids distinct.
- Added regression coverage for event-type-specific id extraction and nullable Postgres lookup
  casts.

## Security and trust boundaries

- This does not enable production customer login.
- Railway production must keep `CPGHERO_CUSTOMER_AUTH_PROVIDER=disabled` until explicit customer
  auth cutover is approved.
- WorkOS remains an authentication provider only; CPGHero remains the authorization source of truth
  for account membership, workspace membership, roles, permissions, entitlements, projects, report
  access, Live API usage limits, and billing.
- Provider subjects and secrets remain internal implementation details and are not customer-facing.

## Explicit non-goals

- Does not create or resend customer invitations.
- Does not grant entitlements.
- Does not add SSO, Directory Sync, or SCIM.
- Does not change reports, proximity metrics, collection requests, product packs, matching, source
  provider calls, PDP calls, AI calls, PDFs, or historical artifacts.

## Verification

- `.venv/bin/pytest apps/api/tests/test_customer_provisioning.py -q`
- `.venv/bin/ruff format --check apps/api/src/rci_api/customer_provisioning.py apps/api/tests/test_customer_provisioning.py`
- `.venv/bin/ruff check apps/api/src/rci_api/customer_provisioning.py apps/api/tests/test_customer_provisioning.py`
- `.venv/bin/pytest apps/api/tests/test_customer_provisioning.py apps/api/tests/test_customer_identity.py apps/api/tests/test_access.py -q`
