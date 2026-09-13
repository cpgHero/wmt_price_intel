# Phase 13.112 — Proximity competitor drawer performance hardening

Date: 2026-09-12

## Summary

The competitor white-space state drawer now keeps the browser preview intentionally compact while preserving complete export coverage. This prevents large state drilldowns for dense retailers from overwhelming the browser or accessibility tree.

## Changes

- Reduced the rendered competitor white-space drawer preview to the first 100 matching rows.
- Preserved full CSV and JSON downloads for the complete matching detail set.
- Updated platform documentation to explain the preview/export distinction.

## Boundaries

This is a Proximity web-rendering, drawer-performance, and documentation refinement only. It does not change API data, location rows, coordinates, retailer eligibility, nearest-location Haversine distance math, product Search evidence, observed product distribution, matching, report calculations, seller rules, provider collection, PDP calls, AI calls, PDFs, or historical artifacts.

## Verification

- `corepack pnpm --filter @rci/web exec prettier --write src/app/proximity/proximity-workspace.tsx`
- `corepack pnpm --filter @rci/web lint`
- `corepack pnpm --filter @rci/web typecheck`
- `corepack pnpm --filter @rci/web test`
- `corepack pnpm --filter @rci/web build`
- `python3 scripts/check_platform_docs_coverage.py --base-ref origin/main`
