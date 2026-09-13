# Phase 14.08 — Customer auth provisioning foundation

Date: 2026-09-13

## Purpose

Create the owner-only CPGHero provisioning layer required before WorkOS/AuthKit customer login can
be safely enabled.

## Implemented scope

- Added migration `0056_customer_auth_provisioning`.
- Added `customer_account_invitation` for prepared customer-account invitations, role keys,
  entitlement keys, optional WorkOS organization/user bindings, and acceptance status.
- Added `customer_identity_webhook_event` for signed WorkOS identity-event audit and replay-safe
  duplicate detection.
- Added `POST /api/v1/admin/customer-provisioning/accounts/prepare`, guarded by the existing
  production admin token, to create or reuse CPGHero organization, account, workspace, app-user,
  membership, role, entitlement, invitation, and optional external-identity rows.
- Added `POST /api/webhooks/workos`, which requires `WORKOS_WEBHOOK_SECRET`, verifies the
  `WorkOS-Signature`, records a payload digest, and processes matching invitation events
  idempotently.
- Kept API responses CPGHero-facing. Provider subject IDs remain internal implementation details.

## Explicit non-goals

- Does not enable `CPGHERO_CUSTOMER_AUTH_PROVIDER=workos` in production.
- Does not send customer invitation emails.
- Does not create WorkOS organizations, users, invitations, SSO connections, Directory Sync, or
  SCIM configuration.
- Does not create customer-facing invite or account-admin screens.
- Does not issue Live API keys.
- Does not change report, proximity, collection, PDP, AI, matching, or historical-artifact behavior.

## Next cutover prerequisites

1. Deploy the signed webhook endpoint.
2. Register the Railway webhook URL in WorkOS and store the returned signing secret in Railway.
3. Prepare a single test customer account and invitation through the owner-only API.
4. Create or invite the matching user in WorkOS.
5. Confirm the webhook activates only the intended CPGHero membership.
6. Run a staged login test with `CPGHERO_CUSTOMER_AUTH_PROVIDER=workos` outside the main production
   customer path, then decide whether to cut production over.
