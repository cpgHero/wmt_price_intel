# Phase 13.19 — Cross-Retailer Price Architecture Matrix

Status: implemented and test-verified; deployment pending

## Outcome

Price Intelligence adds a first-class `Price Architecture Matrix` page beside Home. It examines
the full eligible assortment across all retailers in an analysis without using product matches.
The page answers how each retailer distributes its assortment across Walmart-defined price
positions; it must never imply that products sharing a price band are substitutes.

## Authoritative grain

1. Start from the shared canonical first-party product × retailer-location population.
2. Retain only positive Search package prices. PDP may enrich identity, brand, imagery, and links,
   but cannot override Search price or location.
3. Collapse each retailer product to its median package price across distinct observed locations.
   A SKU therefore contributes once regardless of distribution breadth.
4. Apply optional governed brand-type and location-master state/city/ZIP filters before deriving
   the matrix.
5. Assign each product to exactly one price rung.

## Rung methods

### Walmart-anchored midpoint rungs

- Use the benchmark retailer configured by the immutable analysis; current studies use Walmart.
- Deduplicate equal Walmart SKU median prices into distinct anchor price points.
- Place the boundary between adjacent anchors at the true arithmetic midpoint.
- Use a lower-inclusive, upper-exclusive interval. A price exactly at a boundary enters the
  higher-priced band.
- The first and last bands remain open-ended.

### Fixed bands

- Support stable $0.50 and $1.00 package-price increments.
- Start at zero and retain an open-ended top band.
- Fixed bands are intended for time-consistent architecture comparisons when Walmart price
  changes would otherwise move midpoint boundaries.

## Cell metrics

- **Products + prices:** up to three visible product names and medians, with complete drill-down.
- **SKU count:** number of distinct retailer product IDs assigned to the rung.
- **Percent of assortment:** cell SKU count divided by that retailer's eligible SKU count.
- **Store coverage:** distinct union of eligible retailer locations reached by one or more cell
  products, divided by eligible retailer locations. Individual product coverages are never summed.
- **Average price:** arithmetic mean of the product-level medians in the cell.
- **Price density:** SKU count divided by finite band width. Open-ended bands remain unavailable.

Sales/units are capability-bounded until governed performance data exists.

## Interaction and language rules

- The matrix is available without selecting a product and sits directly beside Home.
- Retailer columns remain horizontally scrollable with the Walmart anchor column pinned.
- Heat intensity is normalized within retailer for the selected metric so a large retailer does not
  visually erase a smaller assortment.
- Clicking a populated cell opens product identity, brand type, image, median/range, observed
  locations, retailer product ID, and retailer URL.
- Empty cells say `No observed SKU in band`. They do not assert a confirmed white-space gap.
- A retailer whose immutable Search evidence is unavailable remains explicitly labeled and cannot
  silently disappear. Missing Walmart evidence blocks the entire matrix because rungs cannot be
  defined.

## Contracts and services

- Normative contract: `schemas/price-architecture-matrix.schema.json` version `1.0.0`.
- API: `GET /api/v1/analyses/{analysis_id}/price-architecture-matrix`.
- Web proxy: `GET /api/price-monitoring/{analysis_id}/architecture-matrix`.
- Rung method, fixed increment, brand type, state, city, and ZIP are explicit request dimensions.
- The API prepares retailer populations with bounded concurrency and caches by immutable
  population checksum plus PDP context revision and selected filters.

## Trust gates

1. Walmart anchor count distinguishes distinct anchor price points from total Walmart SKUs.
2. Duplicate Walmart price points do not create duplicate rungs.
3. Every competitor product is assigned to exactly one rung.
4. True midpoint boundaries and boundary inclusivity are tested.
5. Store coverage uses a distinct location union, not product-location sums.
6. Unsupported price density on open-ended bands remains null.
7. Known third-party products remain excluded by the shared Retailer Pack seller boundary.
8. Matching v2 relationships are not read by this projection.

## Verification

- Deterministic analytics tests cover midpoint math, duplicate anchors, unique SKU assignment,
  boundary behavior, union-based coverage, fixed bands, and schema validation.
- API tests cover the complete filter and rung-method request path.
- Full TypeScript, contract-generation, browser, container, and production validation remain the
  deployment gate.
