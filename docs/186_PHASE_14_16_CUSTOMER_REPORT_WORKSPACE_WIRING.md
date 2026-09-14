# Phase 14.16 — Customer report workspace wiring

Date: 2026-09-14
Status: local verification passed; CI verification pending

## Purpose

Replace the customer report-detail placeholder with the canonical product-level
report workspace while preserving the customer access boundary introduced in
Phase 14.15.

## Changes

- The customer report page loads `/api/customer/reports/{accessId}/report` and
  renders the canonical report workspace from the customer-granted report view.
- The canonical report workspace now accepts a customer access scope.
- In customer mode, dataset JSON, exact-product map evidence, state coverage,
  and evidence CSV routes point to `/api/customer/reports/{accessId}/...`.
- In customer mode, analyst-only `/analyses/...` and `/price-monitoring/...`
  workspace links are hidden.
- The API added customer-report wrappers for the price-monitoring map,
  state-coverage, and evidence CSV read models.

## Access boundary

Every new customer evidence route checks the same predicates before invoking the
read model:

- authenticated CPGHero customer session;
- `analytics.view` permission;
- `app_analytics` entitlement;
- resolved account scope;
- resolved workspace scope;
- active customer report grant;
- ready, non-archived report.

The routes do not expose admin recompute/write routes, global analysis URLs,
internal match or brand workbench mutations, customer API keys, billing
workflows, collection requests, source-provider calls, PDP calls, AI calls,
PDFs, proximity metrics, or historical artifacts.

## Local verification

- `ruff check` and `ruff format` on the changed API files.
- `pytest apps/api/tests/test_customer_reports.py` — 20 passed.
- `pnpm --filter @rci/web lint`
- `pnpm --filter @rci/web typecheck`

## Next step

Run full web build and CI, then deploy. After deployment, smoke-test the
customer report page and verify anonymous users receive 401 responses for the
new customer evidence routes.
