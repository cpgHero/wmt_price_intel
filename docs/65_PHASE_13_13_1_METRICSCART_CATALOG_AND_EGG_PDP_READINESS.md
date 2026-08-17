# Phase 13.13.1 — MetricsCart Catalog and Egg PDP Readiness

## Outcome

Ingest the owner-supplied 2026-08-16 MetricsCart API catalog as auditable, secret-free contracts;
stage Product Details coverage for every retailer in the 14-retailer Egg source; and calculate an
analysis-scoped, cache-adjusted estimate before any paid call is authorized.

This is a prerequisite to the Egg Matching v2 reporting cutover. It does not itself collect PDPs,
change certified relationships, or republish reports.

## Source audit

- Archive: `metricscart-api-catalog-20260816.zip`
- Archive contents: seven files under `metricscart-catalog-export/`
- Catalog: 81 retailers, 217 endpoints, 709 stored endpoint parameters
- Active endpoints: 217
- Endpoints with stored provider samples: 217
- Credential finding: no live credential; `MY_API_KEY` is a placeholder
- Raw package: retained outside Git
- Repository provenance: archive/file SHA-256 values, CRC result, endpoint contracts,
  sample-response hashes, and top-level field inventories

The repeatable importer is `scripts/import_metricscart_catalog.py`. It deliberately does not copy
provider sample bodies into the repository.

## Egg endpoint coverage

The Product Details runtime now has a schema-validated contract for Albertsons, ALDI, Amazon Same
Day, Giant Eagle, H-E-B, Kroger, Meijer, Safeway, Sam's Club, ShopRite, Target, Trader Joe's,
Walmart, and Wegmans. Eight new Retailer Packs make their identity, location, brand, enrichment, and
matching boundaries explicit without enabling their Search adapters.

Generic endpoint defaults cover pickup fulfillment and ShopRite shopping type. Sam's Club sends a
URL instead of the internal canonical product ID because its provider endpoint does not accept a
`product_id`. Request checksums include the effective supported parameters, endpoint path, and
contract version so cache reuse remains correct when provider contracts change.

## Path discrepancies and paid-call gate

Two differences are explicit in `config/metricscart-endpoint-overrides.json`:

1. Amazon endpoint 41 retains the owner-verified trailing slash.
2. Kroger endpoint 105 is fail-closed because the new provider export uses
   `/kroger/pdp/zipcode/` while the prior application catalog used `/mc/kroger/pdp/zipcode`.

No batch may silently choose between conflicting billable routes. Kroger requires an owner-approved
single-call preflight before `paid_calls_enabled` can become true.

## Cost boundary

The attached consolidated Egg Search source contains 1,163 distinct positive-price product IDs
across 14 retailers. Calling one PDP for every one of them without qualification or cache reuse
would be at most 2,362 credits, or $4.724 at the owner-supplied $0.002 per credit. This is a
deliberately conservative ceiling, not the launch amount.

A local read-only reconciliation against the validated Egg product catalog admitted 611 distinct
retailer products. Preserving distinct observed price states produced 890 potential contexts: 848
request-complete contexts totaling 1,755 credits ($3.51) plus 42 blocked Kroger contexts. This
still precedes production cache reuse and is therefore an upper-bound readiness check, not paid-call
authorization.

The production dry-run must further apply:

1. Product Pack admission/noise exclusion.
2. One representative observed ZIP/store per admitted retailer product and additional governed
   contexts only where the enrichment policy requires them.
3. Required-parameter validation and fail-closed endpoint status.
4. Fresh exact-request cache reuse.
5. A separate hard credit ceiling and explicit `--confirm-paid-calls` launch action.

Seller filtering cannot safely remove a never-enriched item from the estimate because seller is a
PDP fact. Known cached non-first-party sellers remain excluded downstream by Retailer Pack policy;
unknown sellers stay unverified until evidence exists.

## Production verification — 2026-08-17

Commit `7ecfd56` passed GitHub Actions run `32043978815`, including the full Python,
TypeScript/browser, migration, contract, build, and four-container matrix. Railway then deployed the
same release successfully to web, API, worker, and scheduler.

The protected production command was executed twice without `--confirm-paid-calls`. Both runs
returned `status=estimate` and `paid_calls_enqueued=0`. The compact reconciliation reported:

- 914 Product Pack-admitted Egg retailer products/offer observations.
- 871 request-valid unique retailer products.
- 527 exact fresh-request cache hits.
- 344 remaining Product Details calls requiring 728 credits, or **$1.456** at $0.002 per credit.
- 43 invalid candidates, all Kroger, blocked before execution by the disputed-path safeguard.
- Eight current candidate product relationships; PDP readiness intentionally covers every admitted
  analysis product, not only already-resolved relationships.

The remaining-credit distribution is:

| Retailer | Calls/credits represented by the contract | Credits |
|---|---:|---:|
| Albertsons | 138 calls at 2 credits | 276 |
| ALDI | 1 call at 1 credit | 1 |
| Amazon Same Day | 4 calls at 2 credits | 8 |
| Giant Eagle | 56 calls at 2 credits | 112 |
| Meijer | 26 calls at 2 credits | 52 |
| Sam's Club | 21 calls at 2 credits | 42 |
| ShopRite | 49 calls at 1 credit | 49 |
| Target | 123 calls at 1 credit | 123 |
| Trader Joe's | 3 calls at 1 credit | 3 |
| Walmart | 22 calls at 1 credit | 22 |
| Wegmans | 20 calls at 2 credits | 40 |
| **Total** | **344 calls** | **728** |

H-E-B, Safeway, and Whole Foods require no new call under the current exact-cache identity. Seller
policy remains enforced whenever PDP seller evidence is known; this estimate cannot pre-filter an
unknown seller without first obtaining its PDP evidence.

## Acceptance tests

- Every Egg retailer resolves to a Product Details endpoint and Retailer Pack.
- ShopRite and Sam's Club requests are created solely from catalog parameters/defaults.
- Leading-zero and hyphenated identifiers remain strings.
- Effective request defaults and contract versions affect cache identity.
- The Kroger conflict rejects planning before a paid request.
- The normalized catalog reconciles to its manifest and versioned 16-row PDP matrix.
- Contract generation, Python tests, TypeScript checks, build, CI, deployment, and a read-only
  production estimate pass before requesting paid-call approval.

## Explicitly deferred

- Paid PDP collection.
- Kroger endpoint preflight.
- Target seller-value activation.
- Egg Matching v2 authoritative cutover and report replay.
