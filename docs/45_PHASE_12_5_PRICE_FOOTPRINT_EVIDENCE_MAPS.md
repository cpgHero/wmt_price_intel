# Phase 12.5 — Price Footprint Evidence Maps

## Objective

Make Price Intelligence maps operationally useful at retailer-location grain without
weakening the Search-evidence governance model or slowing every report tab.

## Implemented behavior

- The Overview map requests an evenly distributed, bounded map projection only when it
  is rendered.
- The Product Footprint tab requests the complete mapped location set for the current
  product and geography.
- Users can toggle between:
  - **Observed** — the exact retailer product appeared in Search with a positive price.
  - **Not observed** — the exact product did not appear in the successful Search result
    for a planned collection location. This remains a review signal, not proof of
    non-carriage.
- Observed points use a two-root price-difference palette relative to the median of the
  visible footprint: blue below median, dark at median, and orange above median.
- Not-observed locations use a distinct gold marker and never receive a fabricated
  price.
- Clicking a state or national location point applies the state filter. The selected
  state's geometry is then fitted to the full map canvas and store points become
  individually selectable.
- Store names, state, city, ZIP, and coordinates come from the retailer location master.

## Service and contract boundary

`GET /api/v1/analyses/{analysis_id}/price-monitoring/map` is a dedicated, cached map
projection. It requires `retailer` and `product_id`, accepts the governed geography and
brand filters, and supports `detail=summary|full`.

The normative response is `schemas/price-monitoring-map.schema.json`. Separating this
projection from the primary Price Monitoring view prevents thousands of map points from
inflating the payload for tabs that do not display a map.

## Trust rules

- Search remains authoritative for current price and observed availability.
- The retailer location master remains authoritative for location attributes.
- Price differences are deterministic and computed from exact-product store evidence.
- A Search non-observation is never labeled out of stock or a confirmed distribution
  gap.
- Missing coordinates are counted in response metadata rather than silently represented
  at an invented location.
