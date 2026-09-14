# Phase 14.14 — Customer report detail and grant administration

## Objective

Let a customer open a report only through an explicit `customer_report_access` grant, and give administrators a controlled way to grant or revoke that access without exposing global report routes.

## Implemented

- Added `GET /api/v1/customer/reports/{access_id}`.
  - Requires a resolved CPGHero customer principal.
  - Requires `analytics.view`.
  - Requires `app_analytics`.
  - Requires resolved account scope.
  - Requires the requested `access_id` to be an active grant for the account and either account-level or matching-workspace scope.
  - Requires the linked `analysis_result` to be non-archived and `reporting_status = 'ready'`.
- Added admin endpoints under `/api/v1/admin/customer-report-access`.
  - `GET` lists current grants and ready, non-archived grantable reports.
  - `POST` grants a ready report by account slug/id and optional workspace slug/id.
  - `DELETE /{access_id}` revokes the grant by setting status to `revoked`; it does not delete the audit row.
- Added same-origin web proxies for the customer detail route and admin grant endpoints.
- Updated `/customer` so granted reports link to `/customer/reports/{access_id}`.
- Added a read-only customer report detail page that renders the grant identity, source checksum, report metadata, available section inventory, and top recorded metrics from the granted payload.
- Added report-publishing admin controls for grantable report selection, account/workspace inputs, grant creation, grant listing, and revocation.

## Trust boundaries

- Customer report detail is keyed by the grant id, not by global `analysis_id`.
- The customer detail page does not embed the internal `/analyses/{analysis_id}` workspace.
- Internal interactive report modules are not customer-visible until their downstream APIs enforce the same account/workspace grant predicates.
- Admin grant creation does not invent an `app_user` actor for token-authenticated admin actions; `granted_by` remains nullable until a real administrator identity exists.
- The customer-auth canary allowlist is unchanged.
- No customer API keys, billing, collection requests, source-provider calls, PDP calls, AI calls, PDFs, proximity metrics, or historical artifacts changed.

## Verification expectation

The local gate must include:

- customer report API tests for detail success and hidden missing/ungranted reports;
- admin report-access tests for token enforcement, snapshot, grant, and revoke;
- web formatting, typecheck, lint, and build;
- platform documentation coverage for the changed web/API files.

## Next recommended step

Choose one customer report module at a time and replace its legacy/global data calls with customer-gated endpoints. The highest-value first targets are customer-safe canonical report dataset, evidence CSV, product footprint/state coverage, and price-monitoring map endpoints because those power the richest report interactions.
