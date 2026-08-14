# Phase 12.10 — Price Intelligence Cohesion

## Outcome

Phase 12.10 removes duplicate single-retailer reporting surfaces and organizes Price Intelligence
around one exact product-location decision flow. No deterministic metric, source-authority rule, or
downloadable evidence is discarded. Detail moves into contextual drawers and a full-screen map.

## Workspace model

1. **Home** selects a retailer product.
2. **Product Overview** combines presence, price, sponsorship, footprint, price-position map, and
   observed/non-observed location evidence.
3. **Price Architecture** combines the exact-product price distribution with geographic price
   structure. Users can switch between a heatmap table and US map and open the complete market
   table in a drawer.
4. **Store Review** combines unusual-price evidence and Search non-observations without conflating
   either with an error or confirmed non-carriage.
5. **Product History** remains unavailable until comparable snapshots exist.

Legacy deep links migrate deterministically: `footprint` → `overview`, `distribution-gaps` and
`store-exceptions` → `store-review`, and `market-benchmarks` → `price-architecture`.

## Metric and source governance

- Search price greater than zero is the module's governed in-stock signal.
- Search `is_sponsored` is the only sponsorship signal.
- Location-master data owns state, city, ZIP, store name, and coordinates.
- Search non-observation remains inconclusive and is never renamed a confirmed distribution gap.
- An unusual-price review uses the 1.5×IQR rule when Q3 is greater than Q1. If IQR is zero, the
  Product Pack tolerance around the modal price is used.
- PDP enrichment supplies identity and imagery only; it cannot override Search price or location.
- The backward-compatible promotion contract remains readable but is intentionally absent from the
  Price Intelligence decision surface.

## Interaction and presentation

- The workspace tab rail remains visible below the 64-pixel application top bar while scrolling.
- Product Overview uses individual location points rather than clusters.
- The map can expand to a near-full-screen dialog and preserves the observed/not-observed mode.
- The location drawer follows the active map mode and provides exact store evidence or planned
  non-observation evidence.
- Current assessment and evidence readiness are available from the top-bar Status & Notifications
  drawer rather than a page-height callout.
- Price Architecture uses one compact distribution panel instead of separate quartile and signal
  card rows.

## Live-ingestion certification boundary

Existing provider-shaped regression fixtures certify positive-price admission, provider ID string
preservation, and `is_sponsored` normalization. A new paid five-category MetricsCart collection is
not required for this UI consolidation and must remain a separately budgeted release-candidate
exercise. When run, it must verify the raw response paths for price and `is_sponsored` for each
enabled retailer before the snapshot is published.

## Acceptance checks

- No Product Footprint, Distribution Gaps, Store Exceptions, or Market Benchmarks tab is rendered.
- Legacy tab URLs resolve to a current workspace.
- Product Overview has no Current Assessment bar.
- Overview map sources are created with clustering disabled.
- Observed/not-observed selection controls both the map and evidence drawer.
- Price Architecture contains no Promotion presentation.
- In-stock and Sponsorship definitions match deterministic Search rules.
- Store Review explains IQR in plain language and preserves exact evidence.
- Product and geography URL context remains aligned across all workspaces and drawers.
