# Phase 13.38 — Fourteen-Retailer Egg Search Expansion

## Objective

Expand the live MetricsCart Search-by-ZIP collection boundary from Walmart, ALDI, and Amazon Same
Day to all fourteen retailers represented in the governed Fresh Shell Eggs benchmark. The expansion
must retain immutable raw responses, positive Search price as availability authority,
`is_sponsored` as sponsorship authority, store/ZIP identity, maximum-credit estimates, and
fail-closed response-contract auditing.

This phase does not authorize a full paid collection. It prepares and verifies the implementation,
then requires a separately estimated and approved bounded provider preflight before any national
launch.

## Catalog authority

The owner-supplied `metricscart-api-catalog-20260816.zip` is the endpoint, parameter, sample-payload,
and credit authority. Its 14 relevant active Search endpoints are:

| Retailer | Endpoint | Credits/page | Location grain | Pagination |
| --- | --- | ---: | --- | --- |
| Walmart | `/mc/walmart/search/zipcode/v2/` | 1 | store + ZIP | yes |
| Albertsons | `/mc/albertsons/serp/zipcode` | 2 | store + ZIP | yes |
| ALDI | `/mc/new_aldi/serp/zipcode` | 2 | store + ZIP | yes |
| Amazon Same Day | `/mc/amazon/search/zipcode/` | 2 | ZIP service area | yes |
| Giant Eagle | `/mc/gianteagle/serp/zipcode/` | 2 | store + ZIP | no |
| H-E-B | `/mc/heb/serp/zipcode/` | 1 | store + ZIP | yes |
| Kroger | `/mc/kroger/search/zipcode` | 3 | store + ZIP | yes |
| Meijer | `/mc/meijer/serp/zipcode` | 2 | store + ZIP | no |
| Safeway | `/mc/safeway/serp/zipcode/` | 2 | store + ZIP | yes |
| Sam's Club | `/mc/samsclub/serp/zipcode` | 2 | store + ZIP | yes |
| ShopRite | `/mc/shoprite/serp/zipcode` | 1 | store + ZIP | no |
| Target | `/mc/target/search/zipcode/` | 4 | store + ZIP | yes |
| Trader Joe's | `/mc/traderjoes/serp/zipcode/` | 1 | store + ZIP | no |
| Wegmans | `/mc/wegmans/serp/store/` | 1 | store + ZIP | yes |

ShopRite receives its catalogued `shopping_type=pickup` default. Amazon Same Day retains URL search
context so general Amazon results cannot replace the Same Day assortment. Store identifiers remain
strings, including Kroger leading zeroes. Target is USA-only and uses its verified store + ZIP
endpoint with `sort=Relevance`.

## Implementation

- The Search adapter registry is catalog-driven. Every retailer marked `enabled` must provide a
  unique adapter ID; adding a retailer no longer requires a hard-coded registry branch.
- Each adapter sends only parameters supported by its endpoint. Required parameters are validated
  before a network request.
- Non-paginated endpoints are fixed to one page in the Collection Builder and are rejected by both
  planning and provider boundaries if a direct definition requests multiple pages. This prevents
  duplicate billable calls with identical inputs.
- The Collection Builder now exposes all enabled retailers, reports whether each endpoint supports
  pagination, and applies availability preflights to selected store-level competitors rather than
  ALDI alone.
- The Postgres rate limiter now keys shared permits and cooldowns by `Search × retailer` under the
  same secret-derived budget key. Multiple worker replicas therefore share each retailer bucket,
  while independent retailers can progress concurrently under the owner-supplied per-retailer,
  per-request-type limit.
- The full MetricsCart catalog sample for every enabled endpoint passes Search response contract
  `1.0.0`, including recognized `results` arrays and required canonical identity fields.

## Location coverage

Production already contains Walmart, Albertsons, ALDI, H-E-B, Kroger, Safeway, and USA Target
locations. The governed location master also contains the missing active USA rosters:

| Retailer | Expected rows |
| --- | ---: |
| Giant Eagle | 200 |
| Meijer | 278 |
| Sam's Club | 609 |
| ShopRite | 330 |
| Trader Joe's | 670 |
| Wegmans | 228 |

These rows must be imported and reconciled after the catalog-driven code is deployed. Existing
approved geography resolutions remain frozen and do not change automatically.

## Verification completed before deployment

- 14 enabled retailer adapters load from the catalog.
- All 14 catalog sample payloads pass the shared Search contract offline.
- Endpoint-specific request tests cover ShopRite pickup and the absence of unsupported page
  parameters.
- Planner and provider tests fail closed on multiple pages for non-paginated endpoints.
- Provider, collection, API, and web tests pass; TypeScript type checking and lint pass.
- No MetricsCart, PDP, or AI call was made during implementation verification.

## Remaining release gates

1. Deploy the implementation and import/reconcile the six missing location rosters.
2. Create one immutable dispersed 14-retailer Egg preflight geography.
3. Produce its exact page, credit, and maximum-dollar estimate.
4. Obtain explicit owner approval and run only that bounded Search preflight.
5. Reconcile raw objects, response contracts, normalized rows, 200/404/nonbillable failures, and
   store/ZIP inputs by retailer.
6. Only after preflight acceptance, produce a new exact full Egg estimate. A national collection
   remains a separate paid approval.
