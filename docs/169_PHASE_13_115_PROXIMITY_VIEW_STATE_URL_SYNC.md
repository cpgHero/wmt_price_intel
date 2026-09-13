# Phase 13.115 — Proximity view-state URL sync

## User-facing problem

- The Proximity page recalculated correctly after an in-page radius or scope
  change, but the browser URL could still show the original query-string
  radius. That made copied links, reloads, and visual troubleshooting less
  trustworthy than the rendered page state.

## Changes

- The Proximity page now parses an optional `scope` query parameter:
  - `all-walmart`
  - `competitor-footprint`
- Client-side view state now writes the active country, competitor, radius, and
  comparison scope back to the URL with `history.replaceState`.
- Invalid or unavailable footprint scope still falls back to the deterministic
  recommended scope for the selected competitor.

## Validation

- Verified locally:
  - `pnpm --filter @rci/web test -- src/app/proximity/proximity-workspace.test.ts`
  - `pnpm --filter @rci/web lint`
  - `pnpm --filter @rci/web typecheck`
  - `pnpm --filter @rci/web build`
- Live production pre-fix check confirmed the original defect: after loading
  H-E-B at 1 mile and changing to 5 miles, rendered H-E-B metrics updated
  correctly but the URL remained `radius=1`.

## Trust boundary

This is a Proximity navigation, sharing, and reproducibility fix only. It does
not change location rows, coordinates, retailer eligibility, nearest-location
pairing, Haversine distance math, map clustering, product Search evidence,
observed product distribution, matching, report calculations, seller rules,
provider collection, PDP calls, AI calls, PDFs, or historical artifacts.
