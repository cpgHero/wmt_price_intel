# Phase 13.108 — Proximity Fast Map Render

Date: 2026-09-12

Status: Local verification passed; production deployment pending.

## Purpose

The Proximity page must show spatial evidence quickly and reliably. A blank map canvas damages trust even when the KPI data has loaded correctly. The previous implementation depended on browser-loaded CDN scripts, external map tiles, and client-side map clustering before the reader saw any meaningful spatial layer. The page also had duplicate page actions in the app shell and on the map surface.

## Changes

- The Proximity API now emits a compact `map_summary` alongside the full row-level pairs.
- `map_summary` contains map bounds plus bounded Walmart and represented-competitor clusters prepared on the backend.
- The Proximity page renders a fast source-backed cluster map immediately from `map_summary`.
- The OpenFreeMap/MapLibre tile layer remains a progressive enhancement and is hidden until it reaches an idle rendered state.
- If OpenFreeMap tiles are slow or unavailable, the reader still sees the cluster map, current coverage, selected relationship, and downloadable row-level evidence.
- Duplicate map-surface action buttons for Controls, fit, fullscreen, settings, and Location table were removed; the native app shell remains the single location for those page-level actions.
- The map surface keeps only the analytical relationship-view toggles: all stores, covered within radius, and white-space stores.

## Metric and evidence boundaries

The fast map summary is derived from the same Walmart-centered nearest-neighbor relationship set as the full Proximity response. It is not a separate source, does not alter nearest-store pairing, and does not change the table/export evidence. Competitor clusters represent selected competitor locations that are nearest to at least one Walmart in the active proximity result; they are intentionally not the full competitor location universe.

## Boundaries

This is a Proximity performance, reliability, map-rendering, and control-hierarchy change only. It does not change location rows, coordinates, retailer eligibility, nearest-location pairing, Haversine distance math, product Search evidence, observed product distribution, matching, report calculations, seller rules, provider collection, PDP calls, AI calls, PDFs, or historical artifacts.

## Verification

- `.venv/bin/ruff check apps/api/src/rci_api/locations.py apps/api/tests/test_locations.py`
- `.venv/bin/pytest apps/api/tests/test_locations.py`
- `corepack pnpm --filter @rci/web lint`
- `corepack pnpm --filter @rci/web typecheck`
- `corepack pnpm --filter @rci/web test`
