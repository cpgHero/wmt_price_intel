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
| Kroger | `/mc/kroger/search/zipcode/` | 3 | store + ZIP | yes |
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
  pagination, and applies availability preflights to the primary retailer plus every selected
  competitor, including ZIP-only Amazon Same Day.
- The Postgres rate limiter now keys shared permits and cooldowns by `Search × retailer` under the
  same secret-derived budget key. Multiple worker replicas therefore share each retailer bucket,
  while independent retailers can progress concurrently under the owner-supplied per-retailer,
  per-request-type limit.
- Availability samples are evaluated and released per retailer. A good retailer can never dilute
  another retailer's 404 rate or be blocked by its failure; an unrecoverable sample stops only that
  retailer's paid remainder as soon as passing becomes mathematically impossible.
- The full MetricsCart catalog sample for every enabled endpoint passes Search response contract
  `1.0.0`, including recognized `results` arrays and required canonical identity fields.
- Location collection eligibility is an explicit, versioned catalog policy. Every imported source
  row remains immutable and queryable, while only active rows whose `Store_No` satisfies the
  retailer's provider-safe format can enter a new geography resolution or billable task.

## Location coverage

Production now contains the complete governed master import: 157,806 rows across 90 resolved
retailer/country identities, with zero skipped rows. The six rosters added for this expansion were:

| Retailer | Expected rows |
| --- | ---: |
| Giant Eagle | 200 |
| Meijer | 278 |
| Sam's Club | 609 |
| ShopRite | 330 |
| Trader Joe's | 670 |
| Wegmans | 228 |

The import also exposed source-representation defects that are unsafe at the provider boundary.
Albertsons contains 377 duplicate/suffixed `Store_No` values containing
`&target=weeklyad`; Wegmans contains 114 composite or spreadsheet-corrupted values alongside 114
numeric provider IDs. The unsafe rows are retained with an exclusion reason. The eligible roster
contains 376 Albertsons and 114 Wegmans stores; all 2,627 ALDI `NNN-NNN` identifiers and all other
enabled physical-retailer numeric identifiers pass policy. Existing approved geography resolutions
remain frozen and do not change automatically.

## Verification completed before deployment

- 14 enabled retailer adapters load from the catalog.
- All 14 catalog sample payloads pass the shared Search contract offline.
- Endpoint-specific request tests cover ShopRite pickup and the absence of unsupported page
  parameters.
- Planner and provider tests fail closed on multiple pages for non-paginated endpoints.
- Provider, collection, API, and web tests pass; TypeScript type checking and lint pass.
- Migration `0045_location_eligibility` backfills the production-safe boundary without deleting or
  rewriting a source row, and new imports calculate the same policy deterministically.
- No MetricsCart, PDP, or AI call was made during implementation verification.

## Remaining release gates

1. Deploy migration `0045`, re-import/reconcile the canonical master, and verify eligible counts.
2. Create a fresh immutable 14-retailer Egg geography; do not reuse the pre-policy snapshot.
3. Produce exact page, credit, and maximum-dollar estimates for both the bounded preflight and the
   requested full run.
4. Obtain explicit owner approval and run only the selected paid Search scope.
5. Reconcile raw objects, response contracts, normalized rows, 200/404/nonbillable failures, and
   store/ZIP inputs by retailer.
6. A national collection remains a separate paid approval even if the bounded preflight passes.
