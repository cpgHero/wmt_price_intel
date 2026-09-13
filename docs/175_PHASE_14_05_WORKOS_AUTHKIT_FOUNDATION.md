# Phase 14.05 — WorkOS AuthKit identity-provider foundation

Status: implemented locally; CI verification pending

Date: 2026-09-13

## Decision

CPGHero will use WorkOS AuthKit/User Management as the production customer authentication provider.

This phase intentionally excludes enterprise SSO, Directory Sync, SCIM provisioning, WorkOS-hosted
RBAC as the authority for application permissions, and any full customer-login cutover.

## Rationale

CPGHero needs secure, multi-tenant customer authentication without turning login, MFA, password
reset, passkeys, session hardening, and recovery workflows into bespoke platform IP. The app's
valuable IP is the retailer data collection, Product Pack governance, matching, analytics,
proximity intelligence, review intelligence, billing governance, and trustworthy reporting layer.

WorkOS AuthKit can own identity proof. CPGHero must still own authorization.

## Implemented scope

- Added a shared non-secret customer-auth configuration model:
  - `CPGHERO_CUSTOMER_AUTH_PROVIDER=disabled|workos`
  - `WORKOS_CLIENT_ID`
  - `WORKOS_REDIRECT_URI`
- Declared WorkOS secret environment names without serializing their values:
  - `WORKOS_API_KEY`
  - `WORKOS_COOKIE_PASSWORD`
  - `WORKOS_WEBHOOK_SECRET`
- Added an additive `external_identity` migration that maps:
  - WorkOS organization subjects to CPGHero `account` rows;
  - WorkOS user subjects to CPGHero `app_user` rows.
- Added tests proving:
  - customer auth is disabled by default;
  - WorkOS can be selected through configuration;
  - secret values are not stored in shared settings objects;
  - unknown auth-provider values fail closed;
  - external identity references require CPGHero account/user bindings.
- Updated internal environment, migration, and Platform Docs references.

## Explicit non-goals

This phase does not:

- create a WorkOS application;
- store real WorkOS credentials;
- enable production customer login;
- add customer signup or invitation screens;
- replace the existing protected internal administrator session;
- add SSO, SCIM, Directory Sync, or WorkOS enterprise-connection billing;
- issue CPGHero Live API keys;
- change account membership, workspace membership, role, entitlement, project, usage, billing, or
  report-access authority;
- change collection requests, provider credentials, reports, proximity metrics, Product Packs,
  matching, paid source calls, PDP calls, or AI calls.

## Security and tenancy interpretation

Authentication and authorization remain deliberately separate:

| Layer | System of record | Purpose |
| --- | --- | --- |
| User authentication | WorkOS AuthKit | Login, email verification, MFA/passkeys/passwordless flows, hosted auth UI, session exchange. |
| Account identity mapping | CPGHero `external_identity` | Map WorkOS user/org subjects to CPGHero-owned user/account records. |
| Authorization | CPGHero database | Account/workspace memberships, roles, permissions, entitlements, project access, usage limits, and billing controls. |
| Internal operations | Existing CPGHero admin principal | Product Pack governance, matching certification, recovery, system operations, and provider administration until the admin-auth cutover is designed. |

This keeps WorkOS replaceable and prevents a third-party identity service from becoming the source
of truth for commercial entitlements or data access.

## Migration contract

`0055_workos_identity_mapping` creates `external_identity` with:

- `provider = 'workos'` as the only allowed provider in this first release;
- `subject_type IN ('user','organization')`;
- a unique provider/subject pair;
- a unique WorkOS organization mapping per CPGHero account;
- a unique WorkOS user mapping per CPGHero user;
- a binding constraint that organization subjects require `account_id` and user subjects require
  `user_id`.

The migration is reversible because no production login data is expected to exist yet.

## Next phase

Phase 14.06 should implement a narrow non-production customer-auth harness and one read-only
account-scoped API route using the new identity seam.

Recommended order:

1. create WorkOS development and production environments outside the repository;
2. configure callback/logout URLs and branded hosted AuthKit;
3. add Next.js auth routes and session verification using WorkOS;
4. upsert `app_user` plus `external_identity` on callback/webhook;
5. resolve a request principal from the session;
6. enforce account/workspace scope on one low-risk read-only route;
7. add cross-account denial tests before expanding route coverage.

