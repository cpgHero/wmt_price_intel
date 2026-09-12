# Phase 13.107 — Proximity OpenFreeMap and Metric Definitions

Date: 2026-09-12

Status: Local verification passed; production deployment pending.

## Purpose

The Proximity page needs to read as a source-backed spatial analytics tool, not as a decorative map mockup. The prior internal SVG/state-outline treatment made the page feel disconnected from the supplied reference and introduced a large visual radius/vignette shape that could be mistaken for data. The Proximity workspace also needed clearer Walmart-centered metric definitions so readers understand exactly what is being counted and why a represented competitor-site count can be lower than the competitor retailer's total footprint.

## Changes

- Proximity now uses the shared MapLibre integration and the OpenFreeMap Liberty style backed by OpenMapTiles and OpenStreetMap contributors.
- The decorative map overlay and SVG-state-map layer are removed from the live map canvas.
- The default selected proximity radius is 1 mile in both the Next.js page normalization and the FastAPI `/api/v1/proximity` default.
- KPI cards now show explicit source-backed labels:
  - total Walmart stores in the selected country from the location master;
  - paired Walmart coverage within the selected radius;
  - paired Walmart white-space beyond the selected radius;
  - competitor locations represented as the nearest selected-competitor site to at least one Walmart location.
- Each KPI includes an info action with the metric rationale, calculation, denominator, and current value.
- The coverage-by-radius card now shows covered Walmart stores, gap stores, and coverage percentage for 1, 3, 5, and 10 miles.
- Map and shell controls include hover title text for button/icon affordances.

## Metric interpretation

The Proximity view remains Walmart-centered. Each paired Walmart location contributes one nearest selected-competitor location. A competitor site can be valid and mappable but still not appear in the represented nearest-site count when it is not the nearest selected-competitor location for any paired Walmart store.

`Total Walmart stores` is the selected-country Walmart location-master count before state, search, relationship, or shortlist filters. The supporting text also discloses how many Walmart locations have valid coordinates and how many are paired to the selected competitor.

`Coverage within radius` is the number of paired Walmart locations whose nearest selected competitor is within the selected radius divided by all paired Walmart locations in the active state/search/shortlist scope. The covered/gap visible-row toggle must not change this denominator.

`White-space stores` is paired Walmart locations minus covered Walmart locations for the selected radius and active state/search/shortlist scope.

`Nearest competitor sites` is the distinct selected-competitor locations represented in nearest-neighbor pairings for the active scope, not the competitor retailer's total mappable footprint.

## Boundaries

This is a Proximity UI, basemap, default-radius, denominator-labeling, hover-affordance, and metric-explanation change only. It does not change location rows, coordinates, retailer eligibility, nearest-location pairing, Haversine distance math, product Search evidence, observed product distribution, matching, report calculations, seller rules, provider collection, PDP calls, AI calls, PDFs, or historical artifacts.

## Verification

- `corepack pnpm --filter @rci/web lint`
- `corepack pnpm --filter @rci/web typecheck`
- `corepack pnpm --filter @rci/web test`
- `corepack pnpm --filter @rci/web build`
- `.venv/bin/pytest apps/api/tests/test_locations.py`
