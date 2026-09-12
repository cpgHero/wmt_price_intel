# Phase 13.109 — Proximity Tile Layer Accessibility

Date: 2026-09-12

Status: Local verification passed; production deployment pending.

## Purpose

The Proximity page uses a fast source-backed cluster map as the default visible spatial layer while the MapLibre/OpenFreeMap tile layer loads in the background. The inactive tile layer must not expose hidden map controls or compete with the fallback map before the enhanced map has actually rendered.

## Changes

- The progressive tile layer is hidden from both the visual layer stack and accessibility tree until the enhanced MapLibre map reaches its rendered idle state.
- Fast cluster marks now expose accessible names with location count, covered-store count, and gap-store count.

## Boundaries

This is a Proximity accessibility and progressive-rendering refinement only. It does not change location rows, coordinates, retailer eligibility, nearest-location pairing, Haversine distance math, product Search evidence, observed product distribution, matching, report calculations, seller rules, provider collection, PDP calls, AI calls, PDFs, or historical artifacts.

## Verification

- `corepack pnpm --filter @rci/web exec prettier --check src/app/proximity/proximity-workspace.tsx src/app/proximity/proximity-workspace.module.css`
- `corepack pnpm --filter @rci/web lint`
- `corepack pnpm --filter @rci/web typecheck`
- `corepack pnpm --filter @rci/web test`
