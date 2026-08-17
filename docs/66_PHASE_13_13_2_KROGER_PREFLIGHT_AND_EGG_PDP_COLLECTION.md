# Phase 13.13.2 — Kroger Preflight and Egg PDP Collection

## Outcome

Resolve the quarantined Kroger Product Details path with one controlled paid call, promote only the
verified contract, recompute the production Egg enrichment plan, and execute the resulting batch
under a hard credit ceiling with durable queue, cache, retry, and audit controls.

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

## Verification ledger

- [x] One controlled Kroger request returned HTTP 200.
- [x] No credential or response body entered Git or application logs.
- [x] Verified route and contract version are encoded in request/cache identity.
- [ ] Full unit, contract, static, browser, build, migration, and container CI passes.
- [ ] Railway deploys the promoted contract.
- [ ] Post-deployment read-only Egg estimate establishes the exact ceiling.
- [ ] Bounded batch is launched and reaches a terminal audited state.
- [ ] Final cache, HTTP-status, credit, normalization, seller, and failure totals are recorded.

## Explicitly deferred

- Matching v2 authoritative cutover.
- Egg report replay and publication/export synchronization.
- Target seller-value activation until live Target evidence is certified.
