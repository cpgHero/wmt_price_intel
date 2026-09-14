# Phase 14.12 — Customer access enforcement seam

## Objective

Add the next safe tenant-readiness layer after successful customer-auth canary login: protected API routes must be able to resolve one CPGHero customer principal and then fail closed on explicit permission, entitlement, account, and workspace checks.

## Implemented

- Added `rci_api.customer_access.current_customer_access_principal`, a FastAPI dependency that reuses the existing `/api/v1/me` customer-principal resolution path.
- Added `rci_api.customer_access.enforce_customer_access`, a narrow helper for route/service boundaries that can enforce:
  - required permission;
  - required entitlement;
  - exact account scope;
  - exact workspace scope.
- Refactored `/api/v1/me` to use the same shared resolver as future protected routes.
- Added route-level tests proving:
  - a correctly scoped WorkOS-backed CPGHero principal is allowed;
  - wrong account scope is denied;
  - wrong workspace scope is denied;
  - missing entitlement is denied;
  - missing permission is denied.

## Trust and security boundaries

- WorkOS remains the identity provider for customer login.
- CPGHero remains the authorization source of truth for account/workspace membership, roles, permissions, entitlements, project access, report access, Live API usage limits, and billing.
- Customer-facing errors remain CPGHero-facing and do not expose identity-provider secrets or provider subject IDs.
- The non-production test-header harness remains blocked in production.

## Explicitly not included

- No broad conversion of existing report, collection, proximity, admin, source-provider, export, Live API, or billing routes.
- No broad customer-auth cutover beyond the existing canary allowlist.
- No customer API-key issuance.
- No report, proximity metric, collection request, source-provider call, PDP call, AI call, PDF, or historical artifact changes.

## Next recommended step

Use this seam to protect the first real customer-owned route with account/workspace predicates. The safest first candidate is a read-only customer project/report listing route backed by data that already carries an account or workspace owner column. Do not expose global report or collection data through customer auth until those predicates are present in the SQL/service layer.
