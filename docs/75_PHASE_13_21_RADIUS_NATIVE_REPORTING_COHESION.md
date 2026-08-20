# Phase 13.21 — Radius-Native Reporting Cohesion

Status: implemented and full local-suite verified; deployment and production validation pending

## Purpose

Reduce duplicated Competitive Intelligence pages, make each visible label agree with its metric,
and carry governed match evidence into retailer, product, geography, and store workflows without
relabeling historical exact-ZIP aggregates as local-radius results.

## Price Intelligence changes

- Home keeps the direct full-report action and removes the duplicate Store Review button.
- Price Architecture Matrix products are ordered by distinct observed-location count, highest
  footprint first, with deterministic tie-breakers.
- Matrix cards and evidence drawers show the PDP seller when supplied and retain the governed
  seller-status label when it is absent.
- Existing publication-time matrix materialization remains authoritative. The product order is
  stored in newly materialized documents, so the UI does not recalculate it.

## Competitive Intelligence information architecture

The report surface is now:

1. Retailer Scorecards
2. Cohort Scorecards
3. Competitive Footprint
4. Matched Price Matrix
5. Match Summary
6. Price Ladders
7. Store Comparisons
8. Competitive History
9. Assortment Scorecards

Market Performance is consolidated into Competitive Footprint. Competitive Exceptions becomes a
toggle inside Store Comparisons. Report-level Data Integrity moves to Operations > Data Quality.
Legacy footprint, market, and exception URLs resolve to the corresponding retained workspace.

## Radius-native retailer scorecards

The immutable publication's historical matched-observation and exact-ZIP aggregates are not
renamed. A separate contract, `competitive-portfolio-scorecards.schema.json`, projects the
certified relationship graph through the same product-leadership engine used by the drilldowns.

For every certified Walmart product and selected competitor, basis, geography, and radius:

1. Start with positive Search observations for the Walmart product at Walmart stores.
2. Retain only certified eligible competitor products under the selected comparison profile.
3. For a physical retailer, select eligible competitor observations within the chosen 1, 3, or 5
   mile radius of each Walmart store.
4. For a service-area retailer, use the same delivery ZIP and label that rule explicitly.
5. Score each Walmart product-location once using the lowest eligible local competitor offer.
6. Aggregate only after the atomic outcomes are complete.

The response reports the denominator and the mutually interpretable outcomes separately:

- `benchmark_lower_rate`: clear Walmart leaders plus narrow Walmart leads among scored
  product-locations.
- `competitor_lower_rate`: competitor-lower outcomes among scored product-locations.
- `parity_rate`: tied outcomes among scored product-locations.
- `leader_rate`: clear Walmart leaders only; it must never be labeled as all Walmart-lower cases.
- `coverage_rate`: scored product-locations divided by observed benchmark product-locations.

Average gap is competitor comparison value minus Walmart comparison value. Positive values favor
Walmart; negative values favor the competitor.

## Workspace behavior

- Competitive Footprint contains the six decision KPIs, individual Walmart and competitor store
  dots, retailer-specific colors, the state/city geographic scorecard, and CSV/Excel exports.
  Cluster bubbles are not used in this governed store view.
- Matched Price Matrix shows only governed matched products under the active retailer, comparison
  basis, radius, and benchmark geography.
- Match Summary orders approved equivalent products by the benchmark-store observations to which
  they contributed and links to Match Certification evidence.
- Price Ladders visually identify the Walmart row.
- Store Comparisons switches between all scored stores and exceptions and exports either current
  view to CSV or Excel-compatible SpreadsheetML.
- Competitive History remains an explicit single-snapshot zero state until another comparable
  certified collection exists.
- Assortment Scorecards use the top-bar competitor context. Assortment breadth is not silently
  represented as a price match.

## Trust and lifecycle rules

- Search owns price and observed product-location evidence; PDP owns descriptive enrichment and
  seller evidence where available.
- Known third-party offers remain excluded through Retailer Pack policy.
- Renderers never recompute authoritative outcomes.
- A zero, no relationship, no local overlap, and unscored evidence remain distinct states.
- Obsolete reports are recoverably archived only after their replacements pass schema, metric,
  navigation, browser, and production reconciliation checks.
- Archival never deletes source Search responses, raw PDP payloads, normalized evidence,
  certification history, immutable releases, or audit lineage.

## Local verification

- 596 Python tests pass; 13 environment-gated Postgres/full-source golden tests skip by design.
- All 66 web and TypeScript contract tests pass.
- TypeScript typecheck, ESLint, JSON contract generation/check, Python Ruff, formatting, and the
  Next.js production build pass.
- Radius portfolio aggregation and JSON Schema validation, Price Architecture Matrix ordering,
  competitive tab identity, legacy-route compatibility, and product-leadership analytics are
  covered by the passing suites.

Full CI, Railway deployment, live browser validation, replacement publication, and recoverable
archive actions remain pending. This document must be updated after those gates complete.
