# Phase 13.110 — Proximity Radius Network UX

Date: 2026-09-12

Status: Local verification passed; production deployment pending.

## Purpose

Improve the Proximity page after owner review by moving radius coverage into the executive summary layer and making selected-store network behavior closer to the supplied proximity explorer reference.

## Changes

- Moved coverage-by-radius out of the map surface into a top summary card immediately below the KPI cards.
- Updated the map legend to describe the marks that are actually rendered: Walmart clusters, represented competitor clusters, selected-network links, and the selected radius.
- Changed the selected radius overlay to center on the selected competitor location, matching the selected competitor network model from the reference explorer.
- Limited rendered relationship lines to the selected competitor network instead of drawing thousands of countrywide links, improving map performance and interpretability.
- Added source-backed selected-network lines and a selected-radius ring to the fast fallback map so the browser shows useful spatial context even before the enhanced OpenFreeMap layer finishes loading.
- Added selected-network counts to the relationship drawer so users can see how many visible Walmart locations are assigned to the selected competitor site and how many are within the active radius.

## Boundaries

This is a Proximity UI, information hierarchy, legend accuracy, selected-network visualization, and performance refinement only. It does not change location rows, coordinates, retailer eligibility, nearest-location pairing, Haversine distance math, product Search evidence, observed product distribution, matching, report calculations, seller rules, provider collection, PDP calls, AI calls, PDFs, or historical artifacts.

## Verification

- `corepack pnpm --filter @rci/web exec prettier --check src/app/proximity/proximity-workspace.tsx src/app/proximity/proximity-workspace.module.css src/lib/platform-docs.ts src/lib/platform-docs.test.ts`
- `corepack pnpm --filter @rci/web lint`
- `corepack pnpm --filter @rci/web typecheck`
- `corepack pnpm --filter @rci/web test`
- `corepack pnpm --filter @rci/web build`

Local rendered verification remained blocked because the standalone local web server could not reach the production API even when launched with Railway environment variables. Production rendering must be verified after deployment against the live Proximity page.
