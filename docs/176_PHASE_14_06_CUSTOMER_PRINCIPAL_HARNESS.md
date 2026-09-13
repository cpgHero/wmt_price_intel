# Phase 14.06 — Customer-principal harness and WorkOS/Railway prep

Status: local verification passed; CI verification pending

Date: 2026-09-13

## Purpose

Create the next safe identity seam after selecting WorkOS AuthKit: CPGHero can now resolve a
validated customer-shaped principal in non-production tests without enabling production customer
login.

This keeps authentication, authorization, tenancy, billing, and data access understandable and
testable before any customer-facing login cutover.

## External setup completed

Using the owner's active WorkOS and Railway sessions:

- WorkOS Staging CPGHero application redirect URIs were configured for:
  - `https://web-production-ee2a4.up.railway.app/api/auth/callback`
  - `http://localhost:3000/api/auth/callback`
- WorkOS Staging application homepage was configured as:
  - `https://web-production-ee2a4.up.railway.app`
- WorkOS Staging initiate-login URI was configured as:
  - `https://web-production-ee2a4.up.railway.app/api/auth/login`
- WorkOS Staging sign-out URI was configured as:
  - `https://web-production-ee2a4.up.railway.app`
- Railway production `web` and `api` services now have preparatory WorkOS variables set:
  - `CPGHERO_CUSTOMER_AUTH_PROVIDER=disabled`
  - `WORKOS_CLIENT_ID`
  - `WORKOS_API_KEY`
  - `WORKOS_COOKIE_PASSWORD`
  - `WORKOS_REDIRECT_URI`

The provider flag deliberately remains disabled. The secret values are stored in Railway and were
not copied into the repository or documented.

## Implemented code scope

- Added runtime role and entitlement registries in `rci_core.access_control` so incoming
  customer principals can validate role and entitlement keys against CPGHero's canonical model.
- Added `require_customer_principal` in `rci_api.access`.
- Added `GET /api/v1/me`, returning:
  - auth provider and source;
  - user ID and email;
  - account ID and workspace ID;
  - CPGHero roles, permissions, and entitlements;
  - `is_system_actor`.
- Added focused API tests proving:
  - the non-production harness is disabled by default;
  - valid test headers resolve the expected customer principal;
  - production rejects test headers even if the harness flag is set;
  - unknown role and entitlement keys fail closed;
  - WorkOS API key and cookie secret values are not serialized.
- Added the non-production harness flag to `.env.example`:
  - `CPGHERO_CUSTOMER_AUTH_TEST_HARNESS_ENABLED=false`

## Security boundaries

The non-production harness is intentionally constrained:

- It requires `CPGHERO_CUSTOMER_AUTH_TEST_HARNESS_ENABLED=true`.
- It is rejected in production regardless of that flag.
- It requires explicit user, email, account, and role headers.
- It validates every role key and entitlement key against CPGHero-owned registries.
- It does not call WorkOS.
- It does not accept arbitrary permissions.
- It does not create users, accounts, memberships, sessions, API keys, projects, or billing state.

## Explicit non-goals

This phase does not:

- enable production customer login;
- turn `CPGHERO_CUSTOMER_AUTH_PROVIDER` to `workos` in Railway;
- create customer signup, invite, logout, callback, or session routes;
- create a WorkOS webhook endpoint or webhook secret;
- add enterprise SSO, SCIM, Directory Sync, or WorkOS-hosted authorization;
- issue CPGHero Live API keys;
- enforce row-level account/workspace scope on report or collection routes;
- change account authorization or billing authority;
- change collection requests, provider credentials, reports, proximity metrics, Product Packs,
  matching, paid source calls, PDP calls, or AI calls.

## Next phase

Phase 14.07 should add the real WorkOS AuthKit callback/session flow behind a feature flag:

1. implement `/api/auth/login`, `/api/auth/callback`, and logout/session helpers;
2. exchange AuthKit authorization codes server-side;
3. map WorkOS user and organization subjects through `external_identity`;
4. create or link CPGHero app users only under explicit account governance;
5. resolve an API principal from the signed session;
6. add a protected read-only account-scoped route with cross-account denial tests;
7. only then consider setting `CPGHERO_CUSTOMER_AUTH_PROVIDER=workos`.
