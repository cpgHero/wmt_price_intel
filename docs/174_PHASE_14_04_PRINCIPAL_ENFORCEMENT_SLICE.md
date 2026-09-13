# Phase 14.04 — Principal resolution and admin enforcement slice

## Purpose

This phase starts moving the API from repeated token checks toward a CPGHero access-principal model without selecting a customer identity provider or changing customer-facing login behavior.

The intent is to make security enforcement easier to reason about before adding broader multi-tenant customer surfaces.

## Scope

Implemented in this phase:

- added a shared API access helper that resolves the existing production admin token into a `system_admin` `AccessPrincipal`;
- preserved the current non-production behavior so local development and test automation remain unblocked;
- centralized feature-enabled admin guards for Product Pack authoring and Matching v2 review;
- reused the shared guard in duplicated admin-only paths for operations, collection recovery controls, PDP evidence export, Product Pack authoring, and Matching v2 review;
- added API tests proving production token enforcement, missing-token denial, non-production permissive behavior, and feature-flag disablement.

Not implemented in this phase:

- customer login;
- SSO;
- invitation or password flows;
- customer API keys;
- account/workspace row-level enforcement on analytical routes;
- account membership lookup from the database;
- support impersonation;
- role-management UI;
- tenant-scoped billing or usage ledgers.

## Why this is intentionally narrow

The app still needs an explicit identity-provider decision before real customer accounts can log in. Choosing that implicitly in a security refactor would be risky.

This phase therefore keeps the existing production admin-token contract but changes the server-side interpretation from "token accepted" to "token accepted and resolved to a CPGHero system principal." That gives the next phase a stable seam for permission and entitlement checks.

## Behavior preserved

- Production admin routes still require `X-RCI-Admin-Token` to match `PRODUCT_PACK_ADMIN_TOKEN`.
- Production with a missing configured admin token still denies admin access.
- Non-production admin routes remain permissive unless a separate feature flag disables the feature.
- Internal service-to-service tokens remain separate from user/admin principals.

## Behavior improved

- Duplicated admin-token comparison logic now lives behind one helper.
- Admin-only routes can now share one principal vocabulary from `rci_core.access_control`.
- Future route dependencies can require permissions from the returned principal rather than inventing per-route authorization strings.
- Feature-disabled paths are evaluated before token acceptance, preserving existing "not enabled" semantics.

## Security interpretation

This is a security foundation slice, not the final multi-tenant security model.

What is now safer:

- token comparison behavior is centralized;
- production token handling has direct regression tests;
- admin token success produces a typed CPGHero principal;
- Product Pack and Matching v2 review enablement checks share one implementation path.

What remains unsafe for customer launch:

- customer sessions are not implemented;
- account memberships are not loaded from the database;
- analytical routes do not yet enforce account/workspace row-level scope;
- API keys and customer usage metering are not implemented;
- support/admin impersonation controls do not exist.

## Next recommended phase

Phase 14.05 should add a non-production customer-principal test harness and route-level account-scope tests for one read-only analytics route. The production customer identity provider should still be chosen before exposing customer login.
