# Phase 13.82 — Positive-price Search store distribution

## Current contract

Store distribution/footprint is the count of distinct, nonblank store IDs for an exact
retailer product when that product is present in a store-level Search result and its
Search price is greater than zero.

```json
{
  "version": "1.0.0",
  "basis": "positive_price_store_search_result",
  "grain": "retailer_product_id_x_store_id",
  "deduplication": "distinct_store_id_per_product",
  "price_rule": "price_gt_zero",
  "inventory_claim": false,
  "stock_status_used": false,
  "sponsorship_used": false
}
```

Stock status, sponsorship, ZIP, location-master membership, planned-store membership,
and inferred geography do not change whether an already-admitted store Search row counts.
Seller and category governance still apply only where they already control admission of
the product Search row. This metric is not an in-stock or inventory metric.

Service-area Search observations are never counted as stores. They are reported separately
as `service_area_presence_count`; store distribution is `distribution_store_count`.

## Reprocessing and publication

Retained positive-price Search evidence is sufficient to rebuild current reports. A current
AnalysisResult must include the versioned contract plus retailer-scoped
`distribution_search_offers`, `distribution_stores`, and `service_area_presence_count`
metrics. Zero is valid; publication does not require positive inventory evidence. Legacy
documents without this explicit contract remain quarantined rather than being reinterpreted.

## Regression invariant

For every product, `distribution_store_count` equals the set cardinality of nonblank store
IDs among its retained positive-price store-level Search rows. A store master cannot add an
unobserved store. The full milk regression fixes Walmart product `46942839` at 83 distinct
stores, all in California in the audited source export.

Contract versions: Price observation `1.3.0`; Price Monitoring view `1.5.0`; map `1.3.0`;
Price Architecture `1.3.0`; Competitive Product Leadership `1.4.0`; product footprint
`1.1.0`; Brand Workbench `1.1.0`.
