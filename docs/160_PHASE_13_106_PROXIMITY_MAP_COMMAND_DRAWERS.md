# Phase 13.106 — Proximity Map Command Drawers

## Objective

Improve the Proximity page user experience after the reference-fidelity release by reducing body chrome, expanding the map workspace, and moving secondary controls/details into drawers.

## Scope

- Move Proximity-specific actions into the native app shell header through application context actions:
  - Shortlist
  - Notes
  - Export
  - Controls
  - Location table
- Remove the permanent left controls rail from the Proximity body.
- Consolidate retailer, radius, state/province, search, relationship, sort, shortlist, and map-layer controls in the right-side controls drawer.
- Replace internal map-view labels with human-readable choices:
  - All stores — show covered and gap locations
  - Covered stores — Walmarts with a nearby competitor
  - Gap stores — no selected competitor nearby
- Enable store clustering by default.
- Strengthen map readability for covered/gap lines, selected-radius rings, selected stores, and cluster marks.
- Replace the tall selected-relationship overlay with a compact selected-store chip that opens a full relationship drawer.

## Non-goals

This phase does not change:

- location rows;
- coordinates;
- retailer eligibility;
- nearest-location pairing;
- Haversine distance math;
- product Search evidence;
- observed product distribution;
- matching;
- report calculations;
- seller rules;
- provider collection;
- PDP calls;
- AI calls;
- PDFs;
- historical artifacts.

## Verification

Local verification passed:

- `pnpm format:check`
- `pnpm --filter @rci/web lint`
- `pnpm --filter @rci/web typecheck`
- `pnpm --filter @rci/web test`
- `pnpm --filter @rci/web build`

Local rendered data verification was blocked because the standalone local web service could not reach the production API. Production rendering must be verified after deployment against the live Proximity page.
