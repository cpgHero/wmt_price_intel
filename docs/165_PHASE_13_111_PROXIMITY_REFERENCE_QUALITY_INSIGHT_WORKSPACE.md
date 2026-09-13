# Phase 13.111 — Proximity reference-quality insight workspace

Date: 2026-09-12

## Summary

Proximity received a deeper map-first information-design pass focused on usefulness, trust, and performance support. The API now returns explicit distance-profile, state-coverage, and competitor-network summaries in addition to the existing Walmart-to-nearest-competitor pair rows and backend map clusters. The web page uses those summaries to expose more actionable spatial insights at the top of the workspace while preserving drawer-based controls and downloadable row-level evidence.

## Changes

- Added backend `distance_summary`, `state_summary`, and `competitor_network_summary` objects to `/api/v1/proximity`.
- Added tests that assert the new summary contract for Walmart-centered coverage, state gaps, and competitor-network assignments.
- Added web API types for the new summary objects.
- Added a top insight deck with:
  - 1/3/5/10-mile Walmart coverage by selected competitor radius.
  - largest white-space states for the active Walmart scope.
  - competitor sites assigned to the most Walmart locations.
  - nearest-distance profile with median, P75, P90, and max.
- Replaced the small selected-relationship toast with a map-side selected-network panel containing selected-pair distance, selected-radius network coverage, median distance, farthest distance, recenter, detail, and table actions.
- Moved the map legend away from the top toolbar and repositioned MapLibre controls to reduce panel/control collisions.
- Updated platform documentation to describe the Proximity page as a reusable location-master analytics surface with backend-prepared summaries and active-filter recalculation.

## Boundaries

This is a Proximity API, UI, information hierarchy, source-definition, and performance-supporting enhancement only. It does not change location rows, coordinates, retailer eligibility, nearest-location pairing, Haversine distance math, product Search evidence, observed product distribution, matching, report calculations, seller rules, provider collection, PDP calls, AI calls, PDFs, or historical artifacts.

## Verification

- `.venv/bin/ruff format apps/api/src/rci_api/locations.py apps/api/tests/test_locations.py`
- `.venv/bin/ruff check apps/api/src/rci_api/locations.py apps/api/tests/test_locations.py`
- `.venv/bin/pytest apps/api/tests/test_locations.py`
- `corepack pnpm --filter @rci/web exec prettier --write src/app/proximity/proximity-workspace.tsx src/app/proximity/proximity-workspace.module.css src/lib/api.ts src/lib/platform-docs.ts src/lib/platform-docs.test.ts`
- `corepack pnpm --filter @rci/web lint`
- `corepack pnpm --filter @rci/web typecheck`
- `corepack pnpm --filter @rci/web test`
- `corepack pnpm --filter @rci/web build`
- `.venv/bin/mypy apps packages/python`
- `python3 scripts/check_platform_docs_coverage.py --base-ref origin/main`
