# Phase 14.13 — Tenant-safe customer report listing

## Objective

Expose the first customer-facing report data path only after adding an explicit account/workspace access grant. Existing internal/global report listings must not become customer-visible simply because customer login works.

## Implemented

- Added migration `0057_customer_report_access`.
- Added `customer_report_access`, an additive grant table that binds:
  - one CPGHero account;
  - optional workspace scope;
  - one immutable `analysis_result`;
  - active/revoked/expired grant status.
- Added partial uniqueness for account-level grants and workspace-level grants so nullable workspace scope cannot create duplicate account-level grants.
- Added `GET /api/v1/customer/reports`.
  - Requires a resolved CPGHero customer principal.
  - Requires `analytics.view`.
  - Requires `app_analytics`.
  - Requires a resolved account.
  - Queries only explicit active grants for that account and either account-level or matching-workspace scope.
- Added a web same-origin proxy at `/api/customer/reports` that forwards customer cookies to the API and returns private no-store JSON.
- Updated `/customer` to show a granted-report panel with an honest empty state when no reports have been deliberately granted.

## Trust boundaries

- The route does not infer access from legacy `organization_id`.
- Existing internal/global report-library and report-detail routes remain unchanged.
- Granted report rows are listed, but opening report detail through a customer-safe route remains future work.
- The customer canary allowlist is unchanged.
- No source-provider calls, PDP calls, AI calls, report recalculation, PDF generation, or historical artifact changes were made.

## Verification expectation

The local gate must include:

- customer report route tests for anonymous denial, scoped success, missing permission, missing entitlement, missing account, and non-production harness support;
- migration upgrade/downgrade through Alembic;
- web lint/build or focused TypeScript tests for the customer workspace and proxy.

## Next recommended step

Add a protected customer report-detail route that requires a matching `customer_report_access` grant before delegating to report rendering/projection. Until then, the customer workspace can safely show which reports are granted without opening the legacy global `/analyses/{analysis_id}` route.
