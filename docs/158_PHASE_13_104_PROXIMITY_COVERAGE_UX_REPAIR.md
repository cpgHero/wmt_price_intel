# Phase 13.104 — Proximity coverage UX repair

Status: local verification passed; production deployment pending

The Proximity page was refocused around the question the page must answer first: how much of the Walmart US or Walmart CA footprint has a selected competitor nearby at useful radius thresholds.

## Scope

- Keep Walmart US or Walmart CA as the fixed benchmark.
- Compare Walmart against exactly one selected competitor retailer from the location master.
- Preserve source-backed nearest-location rows, coordinates, retailer eligibility, selected-radius filtering, and Haversine straight-line distance math.
- Separate the active analysis scope from the covered/gap display toggle so coverage percentages remain stable and trustworthy.

## User-facing changes

- The page now initializes from the broader app dark theme before falling back to the Proximity-specific theme preference.
- The main KPI strip emphasizes Walmart locations in scope, covered locations, uncovered locations, and represented competitor sites.
- The left rail now uses a compact coverage-by-radius matrix for 1, 3, 5, and 10 miles instead of a long nearest-relationships list.
- The long relationship evidence table now opens in a full-height right-side drawer instead of a bottom drawer that pushes content down the page.
- The location details drawer includes summary cards for Walmart locations in scope, covered locations, gaps, and coverage rate, plus CSV, Excel-compatible CSV, JSON, and GeoJSON downloads.
- The map canvas and dark-mode map layers were hardened so map content remains visible in dark mode.
- Narrow app panes now show the KPI strip and map before the longer control rail so the map is not buried below the sidebar controls.

## Non-goals and trust boundaries

- This is a Proximity UI and information-design repair only.
- It does not change location-master rows, coordinates, retailer eligibility, nearest-location pairing, Haversine distance math, product Search evidence, observed product distribution, matching, report calculations, seller rules, provider collection, PDP calls, AI calls, PDFs, or historical artifacts.
- Proximity remains a location-network analytics page. It is not inventory, assortment, product distribution, drive time, or traffic-aware distance.

## Local verification

- `pnpm --filter @rci/web lint`
- `pnpm --filter @rci/web typecheck`
- `pnpm --filter @rci/web build`
