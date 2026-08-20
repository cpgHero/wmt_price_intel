# Phase 13.19 — Cross-Retailer Price Architecture Matrix

Status: refinement implemented; production deployment pending

## Outcome

Price Intelligence adds a first-class `Price Architecture Matrix` page beside Home. It examines
the full eligible assortment across all retailers in an analysis without using product matches.
The page answers how each retailer distributes its assortment across Walmart-defined price
positions; it must never imply that products sharing a price band are substitutes.

## Authoritative grain

1. Start from the shared seller-governed canonical product × retailer-location population. Known
   third-party marketplace sellers are excluded; permitted missing seller values remain explicit.
2. Retain only positive Search package prices. PDP may enrich identity, brand, imagery, and links,
   but cannot override Search price or location.
3. Collapse each retailer product to its median package price across distinct observed locations.
   A SKU therefore contributes once regardless of distribution breadth.
4. Apply optional governed brand-type and location-master state/city/ZIP filters before deriving
   the matrix.
5. Assign each product to exactly one price rung and display the rungs from the lowest Walmart
   price position to the highest.

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
- Bound the visible grid by Walmart's observed assortment and retain open-ended low and high
  edge bands. Competitor outliers therefore remain visible without expanding the matrix into
  hundreds of empty rows.
- Fixed bands are intended for time-consistent architecture comparisons when Walmart price
  changes would otherwise move midpoint boundaries.

## Cell metrics

- **Products + prices:** up to three visible product names and medians, with complete drill-down.
- Product cards also show retailer product ID, distinct observed-location count, and seller status.
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
- Brand type and exact canonical brand filters are independent. Brand filtering changes displayed
  products but preserves Walmart's reference rungs, so a competitor-only brand can still be read
  against Walmart's complete price architecture.
- Known third-party marketplace sellers are excluded. Verified first-party, seller-unverified, and
  non-marketplace/not-governed states remain separate; a blank seller is never called verified.
- Empty cells say `No observed SKU in band`. They do not assert a confirmed white-space gap.
- A retailer whose immutable Search evidence is unavailable remains explicitly labeled and cannot
  silently disappear. Missing Walmart evidence blocks the entire matrix because rungs cannot be
  defined.

## Contracts and services

- Normative contract: `schemas/price-architecture-matrix.schema.json` version `1.1.0`.
- API: `GET /api/v1/analyses/{analysis_id}/price-architecture-matrix`.
- Web proxy: `GET /api/price-monitoring/{analysis_id}/architecture-matrix`.
- Rung method, fixed increment, brand type, exact brand, state, city, and ZIP are explicit request
  dimensions.
- The API prepares retailer populations with bounded concurrency and caches by immutable
  population checksum plus PDP context revision and selected filters.
- Migration `0042_price_architecture_materialization` adds a durable, idempotent JSONB read model.
  Both publication entry points are covered: API publication builds in-process, while the analysis
  worker calls an authenticated API-only endpoint over Railway's private network. They
  pre-materialize the Walmart-anchored, fixed-$0.50, and fixed-$1.00 category matrices; all other
  parameter combinations persist on first use and survive API restarts and replica changes.
  Rebuilding this derivative uses existing Search/PDP evidence and makes no paid provider calls.

## Trust gates

1. Walmart anchor count distinguishes distinct anchor price points from total Walmart SKUs.
2. Duplicate Walmart price points do not create duplicate rungs.
3. Every competitor product is assigned to exactly one rung.
4. True midpoint boundaries and boundary inclusivity are tested.
5. Store coverage uses a distinct location union, not product-location sums.
6. Unsupported price density on open-ended bands remains null.
7. Known third-party products remain excluded by the shared Retailer Pack seller boundary.
8. Matching v2 relationships are not read by this projection.
9. Low-to-high rung order, exact brand filtering, and persisted-read parity are deterministic gates.

## Verification

- Deterministic analytics tests cover midpoint math, duplicate anchors, unique SKU assignment,
  boundary behavior, union-based coverage, fixed bands, and schema validation.
- API tests cover the complete filter and rung-method request path.
- GitHub Actions runs `32304567351` and `32305117053` passed the full Python, contract,
  migration, TypeScript, 13-browser-test, build, and four-container gates.
- The governed Egg analysis was verified in Railway production across all 14 retailers: the
  Walmart-anchored view exposes 83 distinct price points; the fixed $0.50 view exposes 23 useful
  bands from under $1.00 through $11.50+, while retaining competitor outliers in the top band.
- Cell metric switching, private-label filtering, and the product-evidence drawer were exercised
  in the live application. Revision-aware API caching retains the complete retailer set and the
  web proxy does not cache obsolete analytical responses.
