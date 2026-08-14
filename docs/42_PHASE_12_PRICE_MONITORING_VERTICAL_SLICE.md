# Phase 12 — Price Monitoring Vertical Slice

## Objective

Build the first retailer-within-location price monitoring experience on the same governed product,
brand, location, and Search-observation foundation as Competitive Intelligence. This module answers
where a retailer sells each product, at what observed price, across which geographic footprint, and
how that price changes over time. It does not require or calculate a cross-retailer product match.

## Authority and grain

- Search observations are authoritative for retailer, product ID, store or service area, observed
  package price, availability, promotion state when supplied, and observation time.
- PDP enrichment supplies product identity, brand, descriptions, attributes, URLs, and imagery. A
  reusable product identity is enriched once per retailer product and refreshed according to the
  governed enrichment policy—not once per store observation.
- Brand governance supplies `private_label`, `regional`, `national`, or `unclassified`. Brand role
  is always presented with origin and status; a broad footprint never silently converts a brand to
  national.
- Canonical location identity supplies country, state, county, city, ZIP, store number, latitude,
  longitude, and retailer-specific location identifiers where applicable.
- The atomic metric grain is retailer product × retailer location × observation time. Amazon and
  other delivery-area retailers use retailer product × service-area ZIP × observation time and are
  explicitly labeled as non-store observations.

## First dashboard contract

### Global context controls

1. Retailer
2. Product Pack / category
3. Observation period and latest-complete snapshot
4. Brand type: all, private label, regional, national, unclassified
5. Geography level: country, state, city, store or service area

All global analytical state is URL-addressable. Choosing a control applies immediately.

### Default landing view

- Hero status: latest complete observation date, covered locations, observed products, usable-price
  rate, and source freshness.
- Price dispersion: weighted and unweighted median, minimum, maximum, interquartile range, and the
  share of locations at the modal price. Each metric names its denominator and observation grain.
- Distribution: observed locations per product and products per location, split by governed brand
  type.
- Change: products and locations with material price movement versus the previous comparable
  snapshot, clearly separating true movement from additions, removals, and availability changes.
- Quality guardrails: missing or zero prices, unresolved product identity, unclassified brands,
  stale locations, and incomplete snapshots.

### Drillable geography

- Country overview map with state-level price, range, coverage, and freshness summaries.
- State selection drills to cities; city selection drills to individual retailer stores or service
  areas without losing retailer, category, brand-type, product, or date context.
- Map encodings separate median price, range width, coverage, and price-change direction. They are
  never combined into an unexplained composite score.
- Every geographic aggregate opens its underlying products and locations and can export the exact
  Search observations supporting it.

### Product and brand views

- Product cards show PDP identity and imagery, governed brand type, current location count, observed
  price range, median, modal price/share, change since prior comparable snapshot, and data-quality
  status.
- Product drill-through shows a location price distribution, price histogram, geographic map,
  location table, observation history, promotion flags, and source evidence.
- Brand view compares distribution and price dispersion across private-label, regional, national,
  and unclassified portfolios without implying product comparability.
- Brand and product links can open Brand Workbench or identity evidence while preserving retailer,
  category, date, and geography context.

## KPI framework

Primary outcomes:

1. **Price consistency** — share of eligible observed locations within the Product Pack’s configured
   tolerance of the product’s modal or governed reference price.
2. **Price movement** — share and count of continuously observed product-location pairs whose price
   changed versus the previous comparable snapshot.
3. **Distribution coverage** — observed eligible retailer locations divided by expected in-scope
   retailer locations, shown separately from product availability.

Drivers:

- range width and interquartile range by product;
- locations at minimum, modal, and maximum price;
- product distribution breadth by brand type;
- new, discontinued, unavailable, and newly observed product-location pairs.

Guardrails:

- usable-price rate and missing/zero-price exclusions;
- snapshot completeness and freshness;
- unresolved product identity and unclassified brand rates;
- exact counts behind every percentage and visible suppression below minimum sample sizes.

## Shared-foundation benefits for Competitive Intelligence

Price Monitoring becomes the canonical source of retailer-side product/location/time price facts.
Competitive Intelligence consumes those facts and adds governed cross-retailer matching, benchmark
store correspondence, and comparison bases. The shared layer improves:

- regional/private-label product identity and distribution evidence;
- store-level correspondence and 1/3/5-mile overlap analysis;
- price-range and anomaly context before declaring a competitive exception;
- longitudinal confirmation of whether a competitor price gap is persistent or temporary;
- product, brand, geography, and quality drill-through consistency.

## Release sequence

1. Define versioned PriceObservation and PriceMonitoringView JSON contracts.
2. Persist and reconcile product-location observations from existing Search artifacts without new
   MetricsCart collection.
3. Add geography hierarchy and store/service-area facets to the API.
4. Implement retailer/category/period/brand/geography controls and landing dashboard.
5. Implement country → state → city → store mapping and product drill-through.
6. Add prior-snapshot movement after continuous-pair eligibility and snapshot-completeness tests pass.
7. Certify Ground Beef and Milk first; Milk is the primary regional/private-label stress test.
8. Reuse the certified price facts in Competitive Intelligence and validate metric reconciliation.

## Acceptance gates

- Every displayed price resolves to immutable Search evidence and one explicit observation grain.
- Aggregate-to-detail reconciliation is exact for all filters and map levels.
- Brand type is visible, governed, filterable, and never inferred solely from footprint.
- Country, state, city, and store/service-area drill paths preserve context and support evidence
  export.
- A retailer-only metric never depends on a cross-retailer match.
- No new paid provider calls are required for the first vertical-slice replay.

## Implementation status — 2026-08-13

Implemented in the initial vertical slice:

- versioned `PriceObservation` and `PriceMonitoringView` contracts with generated TypeScript types;
- deterministic Search-authoritative projection from immutable classified Parquet artifacts;
- latest-row product × retailer-location deduplication with conflicting-price disclosure;
- governed brand roles from Retailer Packs, the brand foundation, PDP identity, and user overrides;
- retailer, brand-type, state, city, and product URL-addressable filters;
- country/state map, city/location detail, product cards, complete filtered product evidence drawer,
  and CSV download;
- quality checks and source/grain definitions in the primary application;
- checksum validation plus bounded in-process caching of immutable Parquet reads; and
- focused contract, metric, API, navigation, TypeScript, and production-build tests.

Intentionally deferred until a second complete comparable snapshot is certified:

- longitudinal price movement, additions/removals, availability transitions, and historical trends;
- promotion-state analysis where the source provides reliable promotion semantics.

Completed in Phase 12.8:

- Price Monitoring and Competitive Product Leadership now derive from one canonical, versioned
  product-location observation population. See
  `48_PHASE_12_8_SHARED_PRODUCT_LOCATION_INTELLIGENCE_FOUNDATION.md`.
