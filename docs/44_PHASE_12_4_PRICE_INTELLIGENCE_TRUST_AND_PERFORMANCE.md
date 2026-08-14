# Phase 12.4 — Price Intelligence Trust, Geography, and Performance

## Scope

This phase tightens the product-scoped Price Intelligence workspace around the
Search and retailer-location source boundaries and improves interactive
responsiveness.

## Governed metric definitions

- A product is **observed available/in stock** at a retailer location when it
  appears in Search with a USD price greater than zero.
- `is_sponsored` is the only sponsorship signal. Missing sponsorship values are
  unavailable and are never inferred from rank, copy, or price.
- Search owns product presence and store price.
- `retailer_location` owns store name, ZIP code, city, state, country, latitude,
  and longitude. Search location fields identify the lookup key but do not
  override the governed location dimension.
- A planned location where an exact product does not appear is a **Search
  non-observation**. It is useful distribution-review evidence but is not proof
  that the retailer does not carry the product.

## UX and reporting changes

- Added a Home workspace tab containing the retailer product selector.
- Added country → state → city → ZIP → store drill-through.
- Consolidated Product Footprint into Product Overview with an unclustered map, full-screen map,
  and mode-aware observed/non-observed location drawer.
- Reworked maps to use a light, legible base in light and dark application
  themes, price-colored states, city bubbles, and store points at deeper levels.
- Consolidated Distribution Gaps and Store Exceptions into Store Review, with plain-language IQR
  governance and ranked Search non-observation concentration.
- Replaced the duplicate Market Benchmarks workspace with a geographic price heatmap/map toggle in
  Price Architecture; its complete market table opens in a drawer.
- Removed Promotion from the decision surface. In-stock and Sponsorship are the two governed Search
  signals shown alongside price structure.
- Added exact-product sponsorship visibility, geographic breadth, and largest
  non-observation market signals.
- Complete store-level Search evidence remains downloadable as CSV.

## Performance changes

- Removed the redundant client request that repeated the server-rendered initial
  view.
- Added bounded prepared-data and filtered-view caches for immutable analyses.
- Added a client view cache for previously visited product/geography scopes.
- Reduced normal interactive payloads to bounded location evidence while moving
  complete evidence to the CSV endpoint.
- Added a route loading state so cold artifact preparation provides immediate
  feedback.

## Contract changes

`price-monitoring-view.schema.json` is version `1.2.0` and adds:

- explicit location authority;
- ZIP filtering and ZIP geography;
- distribution non-observation geographies and locations;
- sponsorship summaries and store-level sponsorship state.
