# Source Inventory and Known Assumptions

## Supplied sources

1. MetricsCart API documentation/implementation notes supplied by product owner.
2. Representative Walmart, ALDI, Amazon Same Day response shapes supplied by product owner.
3. MetricsCart retailer endpoint credit catalog supplied by product owner.
4. `locations.csv` - 157,806 active location rows / 83 providers.
5. Human-validated competitive-intelligence analyses for eggs, milk, bananas, and strawberries.
6. `CCF_Search_Data_08.03.2026_v2.csv` - 386,889 consolidated egg-search export rows from 14
   retailer domains, attached separately for full golden reconciliation.
7. `metricscart_product_details_by_zipcode_apis.csv` - owner-supplied endpoint, parameter, example,
   and per-success credit details for ten Product Details by ZIP endpoints.

The consolidated egg export is an offline analytical source. Its common 27-column shape is not a
substitute for any retailer's direct MetricsCart SERP or PDP payload. Live adapters remain governed
by retailer-specific API fixtures and endpoint contracts.

## Location observations

- 4,683 Walmart locations; 4,190 normalized U.S. ZIPs.
- 2,627 ALDI locations; 2,499 normalized U.S. ZIPs.
- 2,668 Kroger locations; store identifiers must remain strings.
- Target provider contains both USA and Australia; country filter is mandatory for Target US.
- Some USA ZIP values shorter than five digits require leading-zero normalization.

## API uncertainties intentionally quarantined

- Target: newer catalog lists `/target/search/zipcode`; older snapshot had `/target/search`. Adapter remains disabled/needs verification until a live request confirms parameters.
- Exact provider page-size/has-more semantics are not documented in supplied material. V1 relies on max-pages and stop-on-empty, not guessed short-page pagination.
- The cost catalog gives credits/page but not a dollar conversion; store credits now and add dollar cost only when authoritative credit-to-dollar mapping is provided.
- Product Details by ZIP enrichment remains disabled until retailer response fixtures are supplied;
  the endpoint parameters and credit schedule are now captured in the validated product-detail
  catalog.
