# Phase 13.103 — Proximity reference integration

Status: implementation and release validation

The Proximity page was rebuilt to carry more of the supplied CPGHero proximity-explorer interaction model while preserving the platform's source authority boundaries.

## Scope

- Keep Walmart US or Walmart CA as the fixed benchmark.
- Compare Walmart against exactly one selected competitor retailer from the location master.
- Preserve the existing nearest-location API, Haversine straight-line distance math, retailer eligibility, and filtered-row reconciliation.
- Rebuild the reference experience inside the current app design system rather than embedding the static HTML or copying its static data.

## User-facing changes

- Added top-bar shortlist, notes, export, and light/dark controls.
- Added app-native map layer toggles for Walmart locations, competitor locations, relationship links, selected-radius ring, clusters, and saved-only scope.
- Added real drag, wheel, keyboard, fit, zoom, and fullscreen controls to the SVG map.
- Added hover tooltips, selected-relationship save action, and peer context for the same nearest competitor site.
- Moved the complete evidence table into a bottom drawer with CSV, Excel-compatible CSV, JSON, and GeoJSON downloads.
- Added current-map SVG export for downstream analysis, design review, and future app features.
- Added method and usage modals that state what the proximity data represents and does not represent.

## Non-goals and trust boundaries

- No external CDN street-basemap script was added.
- No iframe or copied static HTML was embedded.
- No product Search evidence, observed product distribution, matching, seller policy, provider collection, PDP call, AI call, PDF, or historical artifact changed.
- Proximity remains a location-master analytics page. It is not inventory, assortment, product distribution, drive time, or traffic-aware distance.

## Verification

- `pnpm --filter @rci/web exec prettier --check src/app/proximity/proximity-workspace.tsx src/app/proximity/proximity-workspace.module.css`
- `pnpm --filter @rci/web typecheck`
- `pnpm --filter @rci/web build`

Production CI, deployment, and live browser/API smoke verification remain required before marking the change order deployed.
