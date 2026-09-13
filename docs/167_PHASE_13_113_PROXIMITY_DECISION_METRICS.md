# Phase 13.113 — Proximity decision metrics

Date: 2026-09-12

## Summary

Proximity now includes market-level decision metrics that are useful to Walmart senior merchandising leaders, buying teams, analysts, suppliers, and brokers. The page keeps the map-first workflow while adding clearer state and city/state rankings for competitive pressure and white-space investigation.

## Changes

- Added backend `market_summary` objects for Walmart-centered city/state proximity coverage.
- Added backend `competitor_market_summary` objects for competitor-centered city/state white-space.
- Added a Competitor white-space markets card and drawer with capped browser preview plus complete CSV/JSON downloads.
- Added Walmart competitive-pressure states that identify where the selected competitor is near the highest share of Walmart stores.
- Added Walmart white-space markets that filter the map/table to city/state Walmart gaps with an explicit reset path.
- Corrected competitor-side KPIs, insight cards, drawers, and exports so active state, search, and shortlist filters are applied to the same competitor-side population.
- Added metric definitions for market white-space and competitive-pressure states.

## Boundaries

This is a Proximity API, filter-scope, metric hierarchy, drilldown, and UX enhancement only. It does not change location rows, coordinates, retailer eligibility, nearest-location Haversine distance math, product Search evidence, observed product distribution, matching, report calculations, seller rules, provider collection, PDP calls, AI calls, PDFs, or historical artifacts.

## Verification

- `corepack pnpm --filter @rci/web exec prettier --write src/app/proximity/proximity-workspace.tsx src/lib/api.ts`
- `.venv/bin/ruff format apps/api/src/rci_api/locations.py apps/api/tests/test_locations.py`
- `.venv/bin/ruff check apps/api/src/rci_api/locations.py apps/api/tests/test_locations.py`
- `.venv/bin/pytest apps/api/tests/test_locations.py`
- `corepack pnpm --filter @rci/web lint`
- `corepack pnpm --filter @rci/web typecheck`
