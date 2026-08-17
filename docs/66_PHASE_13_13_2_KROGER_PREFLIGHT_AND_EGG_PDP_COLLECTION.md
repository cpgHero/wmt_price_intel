# Phase 13.13.2 — Kroger Preflight and Egg PDP Collection

## Outcome

The quarantined Kroger Product Details path was resolved with one controlled paid call. The
verified contract was promoted, the production Egg enrichment plan was recomputed, and the
resulting batch completed under a hard credit ceiling with durable queue, cache, retry, raw-evidence,
and audit controls.

## Controlled preflight — 2026-08-17

The preflight used an Egg product actually observed with a positive Search price:

- Retailer product ID: `0001111060914`
- Product: Kroger Grade A Large White Eggs
- ZIP: `72801`
- Store: `02500624`
- Fulfillment type: `pickup`
- Tested route: `GET https://api.metricscart.com/kroger/pdp/zipcode/`
- Result: HTTP 200, JSON PDP, matching retailer product ID and ZIP
- Seller evidence: `kroger.com`
- Cost: one credit / $0.002

The API key remained in the Railway worker environment and was never printed. The response proved
the owner-supplied catalog route. The previous `/mc/kroger/pdp/zipcode` runtime path is retired.

## Contract promotion

- `config/product-detail-catalog.json` uses `/kroger/pdp/zipcode/`, contract version `2026-08-17`,
  one credit per billable page, and `paid_calls_enabled=true`.
- `config/metricscart-endpoint-overrides.json` records the route as
  `owner_verified_runtime_path` with the preflight provenance.
- Contract and adapter tests preserve the leading-zero UPC and store identifier, exact ZIP,
  fulfillment type, and trailing slash.
- The endpoint schema validates a safe absolute API path instead of assuming every valid provider
  route begins with `/mc/`.
- Changing the route and contract version creates a new exact cache identity; an older response
  from a different contract cannot be silently reused.

## Batch safety boundary

The production plan must be rerun from the deployed contract before launch. The launch command must:

1. Omit Search noise through Product Pack admission.
2. Reuse every fresh exact-request cache entry.
3. Include only request-complete observed product/store/ZIP contexts.
4. Set an explicit `--max-credits` no greater than the verified estimate.
5. Include `--confirm-paid-calls` exactly once to create a durable enrichment run.
6. Let the existing Postgres queue, shared retailer/type limiter, leases, retry policy,
   cancellation, raw-object persistence, and credit ledger govern execution.

Seller evidence is evaluated after normalization. Unknown sellers cannot be removed safely before
the PDP exists; known non-first-party marketplace sellers remain excluded from matching and
reporting under Retailer Pack policy.

## Production execution — 2026-08-17

The deployed, read-only estimate established the exact execution boundary:

- 914 admitted Egg retailer products.
- 527 fresh exact-request cache hits.
- 387 durable jobs requiring a provider call.
- 771-credit / $1.542 maximum batch exposure.
- Zero invalid request contexts after Kroger contract promotion.

The run was created exactly once as `11d33dad-0658-457d-8bdd-b72d2f45a212`. The worker used a
six-job claim limit while the shared Postgres limiter continued to enforce the configured PDP rate
for each retailer.

### Interrupted-response recovery

The first Kroger production responses exposed a snapshot-schema defect: the endpoint catalog
accepted the verified `/kroger/pdp/zipcode/` path, but the downstream snapshot schema still assumed
all provider paths began with `/mc/`. Paid processing was disabled before retrying affected jobs.

The correction and recovery were deliberately fail-closed:

1. The snapshot contract adopted the same safe absolute-path rule as the endpoint catalog and a
   real-shape Kroger response was normalized through both contracts in tests.
2. CI and Railway deployed the corrected contract while paid PDP processing remained disabled.
3. A read-only raw-evidence audit found 49 jobs without a committed current-attempt snapshot:
   nine had immutable response objects and 40 did not.
4. The nine objects classified unambiguously as eight HTTP 200 responses and one HTTP 429 response.
   The recovery recorded all nine without making a MetricsCart request, restored eight missing
   billable credits, and requeued the 429 under the normal cooldown policy.
5. Thirty-six interrupted `running` jobs with no provider-response object were returned to
   `queued`; four jobs already queued after transport failures remained queued.
6. Future S3 PDP response objects now persist HTTP status and response content type in object
   metadata so recovery never needs payload-shape inference for newly collected data.

The recovery command is dry-run by default, refuses `--apply` while
`PRODUCT_DETAIL_ENRICHMENT_ENABLED` is true, rejects ambiguous response shapes, acquires a fresh
recovery lease, and uses the normal snapshot, normalization, canonical-identity, credit-ledger, and
audit paths. It does not construct or import the MetricsCart HTTP client.

## Final production ledger

The durable run reached `completed_with_errors` with no queued or running jobs:

- 269 HTTP 200 successes.
- 117 terminal HTTP 404 failures; 404 responses are billable under the provider contract.
- One terminal HTTP 500 failure after its retry ceiling; it consumed zero credits.
- 769 actual batch credits / $1.538, two credits below the 771-credit ceiling.
- One-credit Kroger preflight / $0.002.
- 770 total phase credits / **$1.540** including the preflight.
- 527 cache hits plus 269 new normalized successes = 796 of 914 admitted products with a reusable
  normalized PDP snapshot for this plan (87.1%).
- All 269 new normalized successes contained a nonblank seller value.

| Retailer | HTTP 200 | HTTP 404 | Other terminal | Credits |
| --- | ---: | ---: | ---: | ---: |
| Albertsons | 84 | 8 | 0 | 276 |
| ALDI | 0 | 1 | 0 | 1 |
| Amazon Same Day | 4 | 0 | 0 | 8 |
| Giant Eagle | 24 | 32 | 0 | 112 |
| Kroger | 43 | 0 | 0 | 43 |
| Meijer | 26 | 0 | 0 | 52 |
| Sam's Club | 0 | 21 | 0 | 42 |
| ShopRite | 47 | 2 | 0 | 49 |
| Target | 0 | 41 | 0 | 123 |
| Trader Joe's | 0 | 3 | 0 | 3 |
| Walmart | 1 | 9 | 1 HTTP 500 | 20 |
| Wegmans | 40 | 0 | 0 | 40 |
| **Total** | **269** | **117** | **1** | **769** |

Kroger completed 43 of 43 planned jobs successfully. Target, Sam's Club, Trader Joe's, ALDI, and
the uncached Walmart subset need retailer-specific request-context or current-availability review
before any paid recollection; a 404 must not be retried merely to improve coverage.

## Verification ledger

- [x] One controlled Kroger request returned HTTP 200.
- [x] No credential or response body entered Git or application logs.
- [x] Verified route and contract version are encoded in request/cache identity.
- [x] Full relevant unit, contract, static, and container CI passes; GitHub Actions run
  `32049626190` completed successfully.
- [x] Railway deployed the promoted contract and the raw-recovery hardening.
- [x] Post-deployment read-only Egg estimate established the exact ceiling.
- [x] Bounded batch launched once and reached a terminal audited state.
- [x] Final cache, HTTP-status, credit, normalization, seller, and failure totals are recorded.

## Explicitly deferred

- Matching v2 authoritative cutover.
- Egg report replay and publication/export synchronization.
- Target seller-value activation until live Target evidence is certified.
