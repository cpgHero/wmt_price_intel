# Phase 13.101 — Proximity Explorer Design Upgrade

## Status

Implemented in code; CI, merge, and production verification pending.

## Trigger

The first production Proximity page was functionally correct but did not meet the visual or interaction quality of the supplied CPGHero Walmart Canada versus Costco Canada proximity explorer. The owner explicitly rejected the page as not close enough to the reference design quality.

## Change

The Proximity page has been redesigned as a map-first explorer:

- full-screen analytical shell with a compact branded top bar;
- focused KPI strip for visible Walmart locations, selected-radius coverage, median nearest distance, and competitor sites represented;
- left control rail with market selector, one-retailer competitor selector, radius selector, search, relationship toggles, sorted pair list, and export access;
- large map stage with coordinate grid, visual land/water treatment, Walmart points, competitor points, nearest-relationship lines, covered/gap styling, floating view controls, legend, status footer, and selected-pair detail card;
- slide-out filter drawer for state/province, relationship, and sort controls;
- slide-out comprehensive location table with CSV, Excel-compatible CSV, and JSON downloads.

The default competitor selection now prioritizes active/catalogued competitors with the largest location footprints instead of choosing the first alphabetical retailer.

The backend nearest-location calculation now uses a deterministic spatial grid to avoid CPU-heavy all-pairs scans for large US retailer footprints. It first finds a nearby candidate from coordinate grid cells, then performs a bounded refinement pass over every competitor location that could beat the seed distance, preserving exact Haversine nearest-location selection.

## Evidence boundary

The page remains source-backed by location-master data:

- Walmart US or Walmart CA is always the benchmark.
- Exactly one non-Walmart competitor retailer is selected.
- The API pairs each mappable Walmart location to its nearest mappable selected-competitor location.
- Distance is Haversine straight-line miles.

The page does not represent drive time, inventory, assortment, or product-level store distribution.

## Non-goals

This redesign does not change:

- source location rows;
- coordinates;
- retailer eligibility;
- proximity distance math;
- product Search evidence;
- observed product distribution;
- matching or certification;
- report price calculations;
- seller governance;
- provider collection;
- PDP or AI calls;
- PDFs or historical artifacts.

## Validation

Required validation before production completion:

- Prettier on Proximity page/component/CSS and platform docs files.
- Platform-docs unit test.
- Platform-docs coverage check.
- CI.
- Production smoke test for `/proximity`, `/api/proximity/retailers?country=USA`, and one Walmart-US-to-competitor proximity payload after deployment.
