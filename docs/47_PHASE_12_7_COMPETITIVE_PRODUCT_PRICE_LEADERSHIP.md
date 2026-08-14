# Phase 12.7 — Competitive Product Price Leadership

## Outcome

Competitive Intelligence now includes a product-anchored, benchmark-store workspace. A reader can
select one benchmark product, one governed comparison basis, one competitor or the full configured
competitor set, and a 1-, 3-, or 5-mile store radius. The same API response drives the overview,
competitive footprint, and store-comparison views so KPI cards, maps, summaries, and rows cannot
silently use different populations.

This is a drill-down within Competitive Intelligence. Price Intelligence remains the source for
single-retailer price and distribution monitoring; Competitive Product Leadership answers whether
the benchmark retailer is winning against governed same-or-similar products at comparable stores.

## Source authority and population

- Search is authoritative for store-specific price and availability. A product observed in Search
  with a positive price is available for this analysis.
- The retailer location master is authoritative for store identity, state, city, ZIP, latitude, and
  longitude.
- Product Pack classification, governed match relationships, and approved human overrides define
  which products are comparable and which price metric applies.
- PDP enrichment may supply product identity and imagery, but it never replaces Search price.
- Duplicate product-location rows are reduced to the latest observation in the collection run.
- Every observed benchmark store remains in the denominator, including stores that cannot be
  scored against a governed competitor observation.

## Geographic comparison rules

Physical competitor stores qualify when they are within the selected 1-, 3-, or 5-mile radius of
the benchmark store. Service-area retailers, including Amazon Same Day, qualify in the same ZIP
because they do not have a comparable physical-store point. Distribution-scoped relationships only
admit the benchmark locations recorded in their governed footprint; a regional product relationship
therefore cannot leak into an unrelated market.

When several governed competitor observations qualify, the lowest comparison value controls the
benchmark-store outcome. Equal values are resolved deterministically by distance and stable location
scope key.

Physical stores are indexed in small latitude/longitude buckets before distance calculation. This
keeps the exact haversine admission rule while avoiding a national all-stores-by-all-stores join.
National responses return state summaries; city summaries are materialized after a state is selected
so the initial payload does not repeat thousands of irrelevant city aggregates.

## Status and metric governance

Each observed benchmark store receives exactly one mutually exclusive status:

- **Leader:** the benchmark comparison value is lower by more than the at-risk threshold.
- **Tied:** the absolute difference is within the Product Pack parity tolerance.
- **At risk:** the benchmark is lower, but its lead is no greater than the at-risk threshold.
- **Losing:** the lowest qualifying competitor comparison value is lower.
- **Unscored:** no current governed matched competitor observation qualifies.

The at-risk threshold is the larger of twice the Product Pack parity tolerance or 2% of the median
benchmark comparison value. Both thresholds, the metric, the unit, and the plain-language status
definitions are returned in the contract.

Coverage rate is scored benchmark stores divided by observed benchmark stores. Leadership rate is
leader stores divided by scored stores. `competitor_minus_benchmark` is positive when the benchmark
is lower and negative when the competitor is lower. The reduction-to-lead value is only populated
for losing stores and includes the parity tolerance needed to move beyond a tie.

## Application workspaces

- **Leadership Overview** presents decision KPIs, an evidence-backed brief, status distribution,
  competitor attribution, and the most urgent states.
- **Competitive Footprint** maps every mappable benchmark store by governed outcome and provides
  state and city drill-downs.
- **Store Comparisons** exposes the benchmark product, competitor product, both prices, distance,
  exact gap, required price reduction, and observation freshness at the evidence grain.

The existing application top bar owns benchmark product, competitor, comparison basis, and radius.
Selections update URL state so a view can be revisited and shared without a second in-page filter bar.

## Contract and API

- Schema: `schemas/competitive-product-leadership.schema.json`
- Example: `examples/competitive-product-leadership.example.json`
- Endpoint: `GET /api/v1/analyses/{analysis_id}/competitive-product-leadership`
- Query context: `competitor`, `profile`, `product`, `radius_miles`, `state`, and `city`

## Deliberately deferred

Competitive History is not presented until multiple comparable collection periods are persisted and
can be reconciled under the same relationship and comparison-rule versions. The current analysis is
a governed snapshot; it must not manufacture persistence or trend claims from one run.

## Verification

```bash
.venv/bin/pytest packages/python/rci-analytics/tests/test_competitive_leadership.py -q
.venv/bin/pytest apps/api/tests/test_analyses.py apps/api/tests/test_price_monitoring.py -q
pnpm contracts:check
pnpm --filter @rci/web typecheck
pnpm --filter @rci/web lint
pnpm --filter @rci/web test
pnpm --filter @rci/web build
```
