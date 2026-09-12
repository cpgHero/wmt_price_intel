# Phase 13.105 — Proximity reference fidelity repair

Status: local lint, TypeScript, and production build passed; production deployment pending.

## Why this change exists

The Proximity page still looked like a light, standalone embedded report inside the dark application shell and did not match the quality of the supplied CPGHero proximity reference. The map also used the full Walmart US network bounds by default, so Alaska, Hawaii, and Puerto Rico distorted the opening continental U.S. view.

## What changed

- Proximity now treats the app shell theme as the source of truth instead of persisting a separate stale page theme.
- Root dark-theme selectors protect the Proximity workspace before and during hydration.
- The duplicate body title/header was collapsed into the native command strip so the page has one integrated header hierarchy.
- The default all-state Walmart US map renders the contiguous U.S. footprint while keeping non-contiguous locations in KPIs, exports, drawer details, and state-specific views.
- Radius coverage now appears as a floating in-map coverage card modeled on the supplied reference explorer.
- The map methodology/status copy now appears in a true bottom status bar rather than another overlay.
- SVG water, land, grid, line, point, and panel colors now use app-native theme tokens instead of hard-coded light fills.

## Boundaries

This is a Proximity UI, theme, layout, and viewport-fidelity repair only. It does not change location rows, coordinates, retailer eligibility, nearest-location pairing, Haversine distance math, product Search evidence, observed product distribution, matching, report calculations, seller rules, provider collection, PDP calls, AI calls, PDFs, or historical artifacts.
