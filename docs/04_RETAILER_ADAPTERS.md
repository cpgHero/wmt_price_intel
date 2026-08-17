# Retailer Adapter Contract

## Separation of concerns

Provider client handles auth, HTTP, global rate-limit permits, retries, request logging, and raw response persistence.
Retailer adapter handles endpoint path, required parameters, location mapping, retailer aliases, request construction, response quirks, and conversion to canonical offers.

## Required adapter methods

```python
class RetailerAdapter(Protocol):
    id: str
    retailer_id: str

    def validate_definition(self, definition) -> list[ValidationIssue]: ...
    def expand_location_units(self, definition, location_repo) -> Iterable[LocationUnit]: ...
    def estimate_pages(self, definition, location_units) -> int: ...
    def build_request(self, task, definition) -> ProviderRequest: ...
    def extract_result_array(self, payload: object) -> list[dict]: ...
    def normalize_result(self, result: dict, context) -> NormalizedOffer: ...
    def should_queue_next_page(self, payload, results, page, max_pages) -> bool: ...
```

## Enabled V1 adapters

### Walmart US
`GET /mc/walmart/search/zipcode/v2/`
- Params: keyword or url, zipcode, store, page, sort, x-api-key.
- Location grain: store + ZIP.
- Credit: 1/page.
- Store selection matters for price/availability.
- The trailing slash is part of the verified direct API route.

### ALDI US
`GET /mc/new_aldi/serp/zipcode`
- Params: keyword, zipcode, store, page, x-api-key.
- Location grain: store + ZIP.
- Credit: 2/page.
- Normalize aliases `new_aldi`, `aldi`, `aldi.us`, `ALDI` -> `aldi_us`.

For every enabled adapter, HTTP 2xx and 404 pages are billable. A 404 is retained as immutable raw
evidence and classified as a nonretryable unavailable/invalid request; it does not become a successful
result page merely because it incurred credits.

### Amazon Same Day US
`GET /mc/amazon/search/zipcode/`
- Params: url, zipcode, page, sort, x-api-key.
- Location grain: ZIP.
- Credit: 2/page.
- The URL input is mandatory in the Same Day adapter. Do not silently replace it with a generic keyword call.

## Response extraction

Generic normalizer checks in order:
`results`, `items`, `products`, `result.results`, `result.items`, `data.results`, `data.items`, `data`.
The adapter may override only if a retailer actually differs.

## Catalogued later adapters

Albertsons, Giant Eagle, H-E-B, Kroger, Meijer, Safeway, Sam's Club, ShopRite, Target,
Trader Joe's, Wegmans, and Walmart Mexico are catalogued in `config/retailer-catalog.json`.
Catalogued means that endpoint metadata, credit cost, aliases, location grain, and a Retailer Pack
exist; it does not mean that Search collection is enabled. Target remains `needs_verification`
because the newer catalog and older endpoint snapshot conflict. Whole Foods Market remains a
normalization-only identity.

## Optional product-detail enrichment

Product Details by ZIP is an implemented, default-off enrichment stage. Owner-supplied Walmart,
ALDI, and Amazon response fixtures govern the three V1 adapters. The 2026-08-16 endpoint/credit
matrix is preserved as a compact, checksummed source manifest and normalized into the shared,
schema-validated `config/product-detail-catalog.json`. It covers 16 PDP endpoints, including all 14
retailers in the Egg source. The complete 217-endpoint provider catalog is retained as endpoint
contracts plus sample-response hashes and field inventories; large provider response bodies stay
outside Git. The runtime design is:

1. SERP collection remains the source of location-specific price, availability, and ranking.
2. After normalization, enqueue at most one PDP request per retailer/product ID and product-version
   key, using a representative successful ZIP/store from the collection as request provenance.
3. Persist the immutable raw PDP payload before deriving descriptions, package attributes, brand,
   identifiers, and product-page evidence into a versioned canonical product record.
4. Reuse a TTL/version cache across collection runs. Request an additional ZIP only when the first
   PDP is unavailable or materially conflicts with SERP evidence.
5. Reserve PDP credits atomically under a per-run ceiling separate from SERP credits. A cached
   snapshot consumes no new reservation and HTTP 200/404 attempts increment the actual ledger.
6. Claim durable jobs with `FOR UPDATE SKIP LOCKED`; expired leases are reclaimable, cancellation is
   durable, and the request checksum is the idempotency key.
7. Enforce rate and cooldown state under a Postgres row lock keyed by credential hash, request type,
   and retailer, so the 3 RPS / 180 RPM limits remain shared across replicas.
8. Resolve required defaults such as `fulfillment_type=pickup` and ShopRite
   `shopping_type=pickup` from endpoint configuration, never category branches.
9. Keep disputed endpoint paths fail-closed until a controlled preflight resolves them. The
   2026-08-17 Kroger preflight returned HTTP 200 for an observed Egg product at
   `/kroger/pdp/zipcode/`; that provider-catalog route is now the only enabled Kroger PDP path.

This stage can power product drill-down and an action queue for high-impact products without
coupling PDP payload shapes to the core analytics engine. Each additional retailer still needs its
own PDP adapter fixture because the consolidated historical export is not an API-response contract.
See `docs/20_PHASE_9_5_4_PRODUCT_IDENTITY_PDP.md` and
`docs/65_PHASE_13_13_1_METRICSCART_CATALOG_AND_EGG_PDP_READINESS.md` for the acceptance ledger.
