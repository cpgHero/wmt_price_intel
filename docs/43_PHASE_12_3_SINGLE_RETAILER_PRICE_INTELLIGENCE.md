# Phase 12.3 — Single-Retailer Price Intelligence

## Outcome

Replace the portfolio-first Price Monitoring page with a product-scoped Price Intelligence
workspace. The module answers how one exact retailer product is priced and observed across the
retailer's governed collection footprint. It does not perform competitor matching.

## Source authority

- Search is authoritative for store/service-area price, location, and explicit availability fields.
- PDP enrichment supplies identity, attributes, URLs, and imagery. It cannot replace Search price.
- A Search non-observation is not proof that a store does not carry a product.
- Sponsorship uses only the Search `is_sponsored` boolean.
- Confirmed distribution gaps require an explicit product-specific retailer signal.
- History compares only snapshots with the same comparability fingerprint.
- Inventory, history, and unsupported availability measures remain unavailable rather than inferred.

## Product-scoped workspaces

1. Product Overview, including footprint, observed/non-observed evidence drawers, and full-screen map
2. Price Architecture, including price distribution and geographic price structure
3. Store Review, combining unusual-price and Search non-observation review queues
4. Product History

The retailer, product, geography, and source-readiness context is persistent. URL parameters are the
analytical source of truth for the selected workspace and filters.

## Deterministic metric definitions

- **Observed presence rate:** locations where the exact retailer product appeared divided by the
  eligible planned collection locations.
- **Median shelf price:** median of positive USD Search prices after selecting the latest
  observation for each exact product-location pair.
- **Price consistency:** share of visible exact-product observations within the Product Pack
  tolerance of that product's modal price.
- **Store exception:** exact-product price outside the 1.5×IQR interval with at least four visible
  observations; when IQR is zero, the Product Pack modal-price tolerance is used.
- **In-stock rate:** an admitted product-location Search observation with a price greater than zero
  is treated as available/in stock. Missing, null, and non-positive prices are not admitted.
- **Sponsorship rate:** `is_sponsored=true` observations divided by Search observations where the
  boolean is known. Missing values remain unavailable.

All analytical calculations are deterministic. AI may summarize validated facts but may not compute
or change metrics.

## Contracts and persistence

`price-monitoring-view.schema.json` retains its backward-compatible promotion summary, but the
Price Intelligence UI does not present promotion as a governed decision signal. Product selection,
observed-presence semantics, deterministic price histograms, sponsorship, and store review all
remain contract-backed. Migration `0027_price_intelligence_foundation` creates the persistent read
model required for comparable snapshot history and durable exception review.

## Current evidence limits

The current release consolidates the product-location workflow into four workspaces. Product
History remains in an honest insufficient-snapshots state until compatible snapshots are
materialized. Store Review shows positive presence and inconclusive non-observations; it does not
fabricate confirmed non-carriage.
Internal region/division/market/store-format reporting is shown only after a governed hierarchy
source populates the new nullable location fields.

## Acceptance checks

- Every product metric reconciles to exact-product store evidence.
- Search price is never overwritten by PDP price.
- Product and geography context remains aligned across all tabs.
- CSV export contains the selected product's visible store evidence.
- Brand type comes from governed brand resolution.
- Unsupported measures are labeled unavailable.
- No competitor fields or matches enter the module.
- Legacy `/price-monitoring` deep links remain usable while `/price-intelligence` is canonical.
