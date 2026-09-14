# Phase 14.15 — Customer-gated report data routes

## Objective

Let granted customer reports load read-only downstream report data without using global `/api/analyses/{analysis_id}` URLs.

## Implemented

- Added customer API routes under `/api/v1/customer/reports/{access_id}`:
  - `GET /report` returns the granted analysis envelope plus its report view.
  - `GET /quality` returns the granted report quality view.
  - `GET /product-decisions/{decision_id}/evidence` returns product decision evidence only after the report grant is authorized.
- Added web routes under `/api/customer/reports/{accessId}`:
  - `/report`
  - `/quality`
  - `/product-decisions/{decisionId}/evidence`, including CSV export parity.
  - `/canonical-report-dataset`, built from the customer-gated report view.

## Trust boundaries

- Every route is keyed by the `customer_report_access.id`, not by global `analysis_id`.
- The grant is resolved before any report-view, quality, or evidence service call runs.
- Routes require customer authentication, `analytics.view`, `app_analytics`, account scope, workspace scope, active grant, ready report status, and a non-archived analysis result.
- Customer write/recompute/admin routes remain unavailable.
- This phase does not change Live API keys, billing, collection, source-provider calls, PDP calls, AI calls, PDFs, proximity metrics, or historical artifacts.

## Verification expectation

- API tests must prove the grant check happens before report-view/evidence service calls.
- Web build/typecheck must include the new customer route files.
- Platform Docs must include the current customer-gated endpoint boundary.

## Next recommended step

Convert one customer-facing report module to call these `/api/customer/reports/{accessId}` routes, then add customer-gated product footprint/state coverage and map endpoints only as their source contracts are verified.
