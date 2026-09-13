# Phase 13.114 — Proximity radius retailer persistence and regional scope

## User-facing problem

- Changing the selected radius after choosing a non-default competitor could
  reload the Proximity workspace with the first/default competitor again.
- Regional competitors such as H-E-B can make national Walmart white-space
  denominators misleading. H-E-B has mappable locations only in Texas in the
  current location master, so all-Walmart U.S. coverage answers a different
  question than "how does Walmart overlap H-E-B's actual footprint?"

## Changes

- Fixed the in-page Proximity loader so radius-only changes preserve the
  currently selected competitor retailer.
- Added a tested selection helper for competitor preservation and safe fallback
  when country changes invalidate the selected retailer.
- Added an explicit comparison-scope model:
  - `all-walmart`: all paired Walmart locations in the selected country.
  - `competitor-footprint`: Walmart locations in states/provinces where the
    selected competitor has mappable locations.
- Regional competitors are recommended into `competitor-footprint` scope when
  their sourced footprint is narrow relative to Walmart's country footprint.
- Added visible scope labeling, a scope control in the controls drawer, and
  scope/method language in metric info modals.
- Kept national scope available so users can intentionally answer the broader
  total-exposure question.

## Validation

- Live data check: `heb_us` has 365 mappable U.S. locations, all in Texas.
- At 1 mile, H-E-B coverage differs materially by denominator:
  - all Walmart U.S.: 114 of 4,683 paired Walmart locations = 2.4%.
  - H-E-B footprint: 114 of 521 Texas Walmart locations = 21.9%.
- Added Vitest regression coverage for:
  - radius-only changes preserving the selected competitor;
  - explicit competitor changes taking effect;
  - invalid country-change selections falling back safely;
  - regional competitors recommending footprint scope;
  - broad competitors retaining all-Walmart scope.
- Verified:
  - `pnpm --filter @rci/web test -- src/app/proximity/proximity-workspace.test.ts`
  - `pnpm --filter @rci/web typecheck`
  - `pnpm --filter @rci/web lint`
  - `pnpm --filter @rci/web build`

## Metric interpretation

The competitor-footprint scope is deliberately state/province based because
those fields are present in the sourced location master. It should not be
described as a trade area, drive-time region, DMA, CBSA, or exact operating
territory until a validated geography source exists.
