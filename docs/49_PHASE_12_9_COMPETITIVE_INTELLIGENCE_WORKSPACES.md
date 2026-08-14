# Phase 12.9 — Competitive Intelligence Product-Leadership Workspaces

## Outcome

The EDLP-inspired product-leadership experience is expanded additively inside Competitive
Intelligence. It does not replace the existing executive report, assortment analysis, governed
match workbench, brand workbench, or exports. Instead, it supplies one product-and-store decision
workspace whose seven views share the canonical Phase 12.8 product-location facts.

## Workspace model

The Product Leadership report tab now contains:

1. **Leadership Overview** — current leader rate, comparable coverage, price exposure, status mix,
   national footprint, and a state watchlist.
2. **Competitive Footprint** — store points colored by mutually exclusive outcome, map drill-down,
   and a state scorecard. Selecting a state scopes every workspace through the shared top context.
3. **Match Group Analysis** — governed relationship count, participating retailer products,
   global versus location-scoped rules, PDP/brand identity, and observed relationship usage.
4. **Store Comparisons** — exact benchmark-store and lowest governed competitor evidence, product
   imagery, brand type, distance, price gap, and reduction required to regain a clear lead.
5. **Market Performance** — state-level leader, loss, and coverage comparisons with an optional
   focused market readout. Loss rates use scored stores; coverage uses observed stores.
6. **Competitive Exceptions** — a current-snapshot queue of undercuts, narrow leads, and stores
   without comparable evidence. It does not label an event persistent or new without history.
7. **Competitive History** — an honest readiness state that records the current baseline and
   explains why one additional certified comparable snapshot is required before trends exist.

Each view has purpose-specific metrics. The same generic KPI strip is not repeated across every
page, and every denominator is disclosed in nearby copy.

Store Comparisons and Competitive Exceptions render 50 evidence rows per page while calculating
filters, totals, and KPIs over the complete response. This keeps large national studies responsive
without sampling or changing the deterministic result.

## Shared context and drill-down

Competitive View, Comparison Basis, Benchmark Product, Store Radius, Benchmark Geography, and
Decision Readiness remain first-class controls in the full-width application context rail.
Selections apply immediately and persist in the URL. A state selection enables city options; a
product change clears stale geography. The seven internal workspaces also persist in the URL.

The map continues to use OpenFreeMap/MapLibre with clustering ending at zoom 4. Physical competitor
stores use the selected 1, 3, or 5 mile radius; service-area retailers use exact ZIP. Search is the
price and availability authority, the retailer location master is the geography authority, and PDP
plus governed Retailer/Brand Packs supply identity context.

## Metric integrity

- Every observed benchmark store has exactly one status: leader, tied, at risk, losing, or
  unscored.
- Leader and loss rates use scored stores; comparable coverage uses observed benchmark stores.
- Market rows reconcile to the currently selected national or geographic result.
- Match-group configuration is distinguished from relationships actually selected by current
  store evidence.
- Exceptions are deterministic projections of current outcomes; no AI-generated or inferred
  metric enters the UI.
- Mixed timezone-aware and timezone-naive provider timestamps are normalized to UTC before latest
  duplicate selection.

## Deferred boundary

Competitive History charts, persistence, week-over-week movement, and new-versus-existing
exceptions remain deferred until at least two complete snapshots have compatible Product Pack,
relationship, geography, retailer, and comparison-basis versions. Export synchronization remains a
separate phase after the primary application tabs are accepted.

## Verification

```bash
.venv/bin/pytest packages/python/rci-analytics/tests/test_product_location.py \
  packages/python/rci-analytics/tests/test_competitive_leadership.py \
  apps/api/tests/test_price_monitoring.py apps/api/tests/test_analyses.py
pnpm --filter @rci/web test
pnpm --filter @rci/web typecheck
pnpm --filter @rci/web lint
pnpm --filter @rci/web build
```
