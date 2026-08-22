# Source Inventory and Known Assumptions

## Supplied sources

1. MetricsCart API documentation/implementation notes supplied by product owner.
2. Representative Walmart, ALDI, Amazon Same Day response shapes supplied by product owner.
3. MetricsCart retailer endpoint credit catalog supplied by product owner.
4. `locations.csv` - 157,806 active location rows / 83 providers. Its ALDI subset is refreshed
   from the owner-supplied 2026-08-22 MetricsCart roster retained at
   `fixtures/location_master/retailer_updates/aldi-locations-2026-08-22.csv` (2,627 rows; SHA-256
   `6ee18a8a5679d085697253e280620e0120b2f3a48467b5af501acee82947fee6`).
5. Human-validated competitive-intelligence analyses for eggs, milk, bananas, and strawberries.
6. `CCF_Search_Data_08.03.2026_v2.csv` - 386,889 consolidated egg-search export rows from 14
   retailer domains, attached separately for full golden reconciliation.
7. `metricscart-api-catalog-20260816.zip` - owner-supplied catalog of 81 retailer sources, 217
   active endpoints, 709 provider parameters, and 217 stored sample responses. The archive remains
   outside Git; its checksum/file inventory is committed in
   `source_material/metricscart-api-catalog-20260816.manifest.json`.
8. `metricscart_product_details_by_zipcode_apis_20260816.csv` - normalized endpoint, parameter,
   sample-response hash, and credit details for the 16 Product Details by ZIP endpoints currently
   staged by the application, including all 14 Egg retailers.

The consolidated egg export is an offline analytical source. Its common 27-column shape is not a
substitute for any retailer's direct MetricsCart SERP or PDP payload. Live adapters remain governed
by retailer-specific API fixtures and endpoint contracts.

## Location observations

- 4,683 Walmart locations; 4,190 normalized U.S. ZIPs.
- 2,627 ALDI locations; 2,499 normalized U.S. ZIPs.
- The 2026-08-22 ALDI refresh preserves the same 2,627 store-number/physical-location universe and
  corrects 79 MetricsCart location IDs in leading-zero-ZIP states. It does not change the tested
  ALDI Search store/ZIP pairs and therefore does not, by itself, resolve regional 404s.
- Eleven exact-address/coordinate ALDI collisions contain two active store numbers each in North
  Carolina. They remain an explicit governance exception; do not silently collect both or retire
  either identifier without callability evidence.
- 2,668 Kroger locations; store identifiers must remain strings.
- Target provider contains both USA and Australia; country filter is mandatory for Target US.
- Some USA ZIP values shorter than five digits require leading-zero normalization.

## API uncertainties intentionally quarantined

- Target: newer catalog lists `/target/search/zipcode`; older snapshot had `/target/search`. Adapter remains disabled/needs verification until a live request confirms parameters.
- Exact provider page-size/has-more semantics are not documented in supplied material. V1 relies on max-pages and stop-on-empty, not guessed short-page pagination.
- The cost catalog gives credits/page but not a dollar conversion; store credits now and add dollar cost only when authoritative credit-to-dollar mapping is provided.
- Product Details by ZIP remains an explicitly approved, separately capped workflow. Dry-run plans
  exclude Product Pack noise, validate request completeness, reuse exact fresh cache entries, and
  make no provider calls. Known marketplace sellers are excluded once governed PDP seller evidence
  exists; missing PDP seller evidence cannot be pre-filtered without making the very call being
  estimated.
- The 2026-08-16 Kroger PDP path originally conflicted with the previously staged route. A
  controlled 2026-08-17 call for Egg product `0001111060914`, observed at ZIP `72801` / store
  `02500624`, returned HTTP 200 at `/kroger/pdp/zipcode/`. The prior `/mc` route is retired.
- No CI test calls the live provider. Provider samples validate field inventories and normalization
  breadth but do not replace owner-approved live endpoint certification.
