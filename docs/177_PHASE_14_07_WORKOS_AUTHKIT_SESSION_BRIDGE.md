# Phase 14.07 — WorkOS AuthKit session bridge

Status: local verification passed; CI verification pending

Date: 2026-09-13

## Purpose

Implement the real WorkOS AuthKit login/session seam without turning on production customer access.

The goal is to prove the auth path end-to-end in code while preserving the CPGHero authorization
boundary: WorkOS authenticates the person, but CPGHero database records decide account membership,
workspace membership, roles, permissions, entitlements, report access, project access, Live API
usage limits, and billing.

## Implemented code scope

- Added the official WorkOS Python SDK to the API service.
- Added `/api/auth/login`.
  - Generates WorkOS PKCE verifier/challenge values.
  - Stores state, verifier, return path, and timestamp in a short-lived encrypted HttpOnly flow
    cookie.
  - Redirects to WorkOS hosted AuthKit.
- Added `/api/auth/callback`.
  - Requires both `code` and `state`.
  - Rejects missing, expired, or mismatched flow cookies.
  - Exchanges the authorization code server-side.
  - Stores a sealed CPGHero customer session cookie.
  - Redirects only to safe same-site relative paths.
- Added `/api/auth/logout`.
  - Clears the CPGHero customer session and auth-flow cookies.
  - Uses the WorkOS logout URL when a valid session can produce one.
- Extended `/api/v1/me`.
  - When the provider is disabled, it keeps the explicit non-production test harness behavior.
  - When the provider is `workos`, it validates the sealed WorkOS session and resolves it through
    CPGHero database rows.
  - The customer-visible response stays CPGHero-facing and does not expose WorkOS credentials,
    cookie secrets, or provider subject IDs.
- Added Next.js same-origin proxy routes for:
  - `/api/auth/login`
  - `/api/auth/callback`
  - `/api/auth/logout`
  - `/api/auth/me`
- Added a Postgres principal resolver that maps:
  - WorkOS user subject → CPGHero `app_user` through `external_identity`;
  - WorkOS organization subject → CPGHero `account` through `external_identity`;
  - active `account_membership` and `workspace_membership` rows → principal account/workspace;
  - governed `platform_role` rows → runtime role and permission keys;
  - active `account_entitlement` rows → runtime entitlement keys.

## Security boundaries

- Railway production still leaves `CPGHERO_CUSTOMER_AUTH_PROVIDER=disabled`.
- No production customer login is enabled by this code change alone.
- Unknown or unmapped WorkOS users fail closed.
- Unknown or unmapped WorkOS organizations fail closed.
- Users in multiple accounts require WorkOS organization selection rather than arbitrary fallback.
- Unknown CPGHero role or entitlement keys fail closed.
- Test principal headers remain non-production only.
- Auth cookies are HttpOnly, SameSite=Lax, and Secure in production.
- Auth flow return paths are restricted to same-site relative paths to prevent open redirects.
- The cookie password must be a Fernet-compatible urlsafe base64 32-byte key.

## Explicit non-goals

This phase does not:

- turn `CPGHERO_CUSTOMER_AUTH_PROVIDER` to `workos` in Railway;
- provision real customer users or accounts;
- create customer signup or invite screens;
- create a WorkOS webhook endpoint or webhook secret;
- issue customer Live API keys;
- add customer account-management screens;
- enforce account/workspace scope on existing report, collection, proximity, or admin routes;
- add enterprise SSO, Directory Sync, or SCIM;
- change collection requests, reports, proximity metrics, Product Packs, matching, source-provider
  credentials, paid source calls, PDP calls, AI calls, PDFs, or historical artifacts.

## Next phase

Before enabling production customer auth:

1. create explicit account/user provisioning or invitation workflows;
2. provision at least one internal/customer account with `external_identity` mappings;
3. add a WorkOS webhook endpoint only after a real dashboard webhook can provide its signing secret;
4. add one protected customer route with account-scope denial tests;
5. add account switch/organization-selection UX if a user can belong to more than one account;
6. run a production dry run against a mapped internal user;
7. then consider setting `CPGHERO_CUSTOMER_AUTH_PROVIDER=workos`.
