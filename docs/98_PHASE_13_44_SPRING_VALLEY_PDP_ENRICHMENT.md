# Phase 13.44 — Spring Valley PDP Enrichment

## Current Outcome

The platform owner approved a hard **$15.00** Product Details ceiling on August 23, 2026. At the governed MetricsCart rate of $0.002 per credit, the durable database ceiling is **7,500 credits**.

The final production estimate re-read the immutable live Search artifacts and exact Product Pack `vitamins_supplements@1.0.2` immediately before launch. It remained below the approved ceiling:

| Measure | Final production result |
|---|---:|
| Governed distinct products | 2,431 |
| Valid retailer PDP contracts | 2,431 |
| Endpoint-ineligible products | 0 |
| Fresh exact-context cache hits | 0 |
| Planned calls | 2,431 |
| Planned credits | 5,336 |
| Maximum provider cost | $10.67 |
| Approved credit ceiling | 7,500 |
| Approved dollar ceiling | $15.00 |
| Raw Search checksum failures | 0 |

Durable Product Details run `9e03fc83-8e2f-4700-9464-d951021ebac7` completed with errors on August 23, 2026:

| Final result | Count |
|---|---:|
| Normalized HTTP 200 products | 1,816 |
| Explicit failed products | 615 |
| Actual credits | 4,578 |
| Actual provider cost | $9.156 |

Amazon Same Day, Costco, Kroger, Sam's Club, and Walmart completed without a failed product. Meijer retained eight non-billable timeouts, Target retained two billable 404s, BJ's retained 56 billable 404s, CVS retained 178 billable 404s, and Walgreens returned 371 non-billable HTTP 400 responses.

A controlled Walgreens diagnostic identified a contract-context defect: live Search described the offer as `SFS`, while MetricsCart's Walgreens PDP route requires `fulfillment_type=pickup`. The identical product ID `300391652`, ZIP `43230`, and store `9093` returned HTTP 200 when only fulfillment changed to `pickup`. The diagnostic consumed two credits ($0.004) within the existing owner-approved ceiling.

## Governing Source Runs

- Main nine-retailer Search: `e962ced9-9e83-4cf3-b5f2-2cf514009ae3`
- Kroger recovery Search: `3093b480-d633-4f61-af47-ba499a355bb9`
- Product Pack: `vitamins_supplements@1.0.2`

Each canonical-product context records both Search run IDs, the exact Product Pack version, the Search offer ID, observed ZIP and store, fulfillment context, observed Search price, and the reason the representative PDP was selected. Search remains authoritative for store price and observed availability.

## Paid-Call Safeguards

The live launcher:

1. converts the owner-approved USD amount to an integer credit ceiling without rounding up;
2. verifies every immutable Search artifact checksum;
3. reclassifies every product with the exact governed Product Pack;
4. selects one positive-price representative observation per retailer product;
5. validates every request against the versioned retailer PDP catalog;
6. rechecks the 30-day exact-context normalized HTTP 200 cache;
7. fails closed if the calculated plan exceeds the approved ceiling;
8. refuses a duplicate launch when the same request checksum is already queued or running; and
9. relies on the durable Postgres queue, leases, retries, cancellation, and per-retailer shared rate limiter for execution.

The corrective release adds catalog-level fixed parameters, so provider-required request values override incompatible observation vocabulary without a retailer branch in the engine. It also claims jobs fairly across retailers within priority and raises default batch concurrency to 18. Each retailer retains its independent globally shared 3-request-per-second and 180-request-per-minute ceiling.

No AI task is created by this phase.

## Current Limitation

The underlying Meijer Search evidence remains partial at 40 successful requests out of 85. PDP enrichment can improve identity evidence for the products that were observed, but it cannot reconstruct the 45 unavailable Search pages or assert assortment absence. Reporting must retain the Meijer partial-coverage disclosure.

## Completion Gate

Before Matching v2 candidate generation begins, the completed run must be reconciled by retailer and HTTP status. The next gate will:

- verify actual credits remain at or below 7,500;
- retain every immutable PDP response, including billable 404 evidence;
- normalize the complete useful PDP field set;
- apply first-party seller governance before matching;
- summarize PDP field completeness and unmapped schema evidence;
- extract governed supplement specifications, unit-price inputs, markdown evidence, and certification evidence; and
- keep unresolved identity or seller evidence visible rather than silently coercing it.
