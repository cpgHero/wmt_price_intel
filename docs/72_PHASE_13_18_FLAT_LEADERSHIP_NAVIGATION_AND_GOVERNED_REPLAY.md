# Phase 13.18 — Flat Leadership Navigation and Governed Replay

Status: implementation in progress

## Outcome

Competitive Intelligence removes the nested Product Leadership workspace rail. Its eight views
become first-class report tabs so one tab selection always identifies the visible analytical
workspace.

## First-class report order

1. Executive Overview
2. Price Architecture
3. Leadership Overview
4. Competitive Footprint
5. Match Group Analysis
6. Price Ladders
7. Store Comparisons
8. Market Performance
9. Competitive Exceptions
10. Competitive History
11. Assortment & Whitespace
12. Data Integrity

The leadership tabs retain one shared context: competitor retailer, comparison basis, benchmark
product, 1/3/5-mile radius, benchmark state, and benchmark city. Switching a leadership tab does
not reset that context.

## Compatibility

Legacy links using `tab=product-leadership` and an optional `leadership` value are translated to
the corresponding first-class tab. The obsolete `leadership` query parameter is removed from the
normalized URL. No metric, relationship, location, or evidence contract is changed by the
navigation refactor.

## Governed Egg replay

After the navigation deployment passes CI, the current complete Egg certification gold set will
be replayed from its immutable source analysis. The replay must:

- disable automatic match fallback;
- include certified comparable relationships only in price comparisons;
- preserve certified not-comparable decisions as exclusions;
- reconcile certified and unresolved counts to the release coverage contract;
- regenerate retailer/cohort product evidence with current brand governance; and
- publish new immutable analysis and report identifiers instead of mutating the prior report.

The radius-based Product Leadership API remains authoritative for physical-store 1/3/5-mile
reporting and same-ZIP service-area reporting. Legacy exact-ZIP scorecards may be retired only when
their replacement portfolio/cohort read models have equivalent certification and reconciliation
tests; a replay must not merely relabel old ZIP metrics as radius metrics.

## Trust gates

1. Exactly one main report tab is selected and no nested Product Leadership tab rail is rendered.
2. All eight leadership tabs retain the selected product, competitor, basis, radius, state, and
   city.
3. Legacy Product Leadership URLs resolve to the intended first-class tab.
4. Replay certification coverage reconciles exactly to the immutable queue and gold set.
5. Known third-party products remain excluded under Retailer Pack seller policy.
6. Brand-type summaries are sourced from governed product identity; unresolved types stay labeled
   rather than inferred.
7. For physical retailers, comparable-store counts are monotonic across 1, 3, and 5 miles for an
   unchanged relationship and benchmark footprint.
8. First-load latency and cached-load latency are measured separately; a slow request may not
   yield a partial or stale result.
