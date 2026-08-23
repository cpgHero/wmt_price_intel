# Phase 13.43 — Spring Valley Search Readiness Audit

## Outcome

The Spring Valley Search evidence is ready for a separately approved, cache-aware PDP enrichment step. This phase did not launch paid PDP or AI work.

The audit covers:

- main Search run `e962ced9-9e83-4cf3-b5f2-2cf514009ae3`;
- Kroger recovery run `3093b480-d633-4f61-af47-ba499a355bb9`;
- Product Pack `vitamins_supplements@1.0.2`;
- one governed PDP candidate per distinct retailer and retailer product ID;
- exact-request-context PDP cache checks under the 30-day freshness policy.

## Audited Result

| Measure | Result |
|---|---:|
| Collection tasks | 850 |
| Successful tasks | 803 |
| Failed tasks | 47 |
| Task success rate | 94.5% |
| Raw Search rows | 20,314 |
| Distinct raw retailer products | 8,430 |
| Governed Search-admitted products | 2,431 |
| Valid PDP request contracts | 2,431 |
| Endpoint-ineligible products | 0 |
| Exact-context fresh PDP cache hits | 0 |
| Worst-case PDP credits | 5,336 |
| Worst-case cost at $0.002/credit | $10.67 |
| Raw artifact checksum failures | 0 |

The cost is an approval estimate, not a charge. The executor must recheck the 30-day cache immediately before enqueueing and call only products that still lack a valid exact-context snapshot.

## Retailer Coverage

Nine retailers completed at least 84 of 85 Search tasks. Meijer completed 40 of 85 and must remain visibly marked partial until its 45 failed tasks are recovered or accepted as a known limitation.

The exact retailer evidence is stored in `artifacts/spring-valley-search-audit/retailer-summary.csv` and the portable audit report.

## Search Schema Findings

The successful Search payloads provided complete mapped coverage for product identity, URL, primary image, and price fields across all ten retailers.

Search is not sufficient for final product admission:

- seller was absent on every Search row;
- brand was entirely absent for Amazon Same Day, BJ's, Meijer, Sam's Club, and Walmart;
- sponsorship was entirely absent for BJ's, Costco, Meijer, and Walgreens;
- Walmart Search scope is therefore constrained by the supplied Spring Valley product-ID allowlist;
- Walmart, Target, and Amazon first-party governance must use normalized PDP seller evidence before matching and reporting.

Blank PDP seller evidence may remain provisionally eligible only under the governed Retailer Pack policy. A positive non-first-party seller must be excluded before matching.

## Product Pack 1.0.2

The raw Search audit proved that specific non-supplement products could pass the earlier title scope. Version 1.0.2 adds narrow exclusions for pet supplements, topical formulas, serum, moisturizer, conditioner, sunscreen, body lotion, cleanser, orange juice, juice drinks, and tea bags.

The scope remains intentionally category-generic. It does not exclude broad terms such as `skin care`, because legitimate oral hair, skin, and nails supplements use that language. Regression coverage verifies both the new exclusions and retention of a valid oral vitamin product.

## PDP Catalog Reconciliation

The supplied MetricsCart catalog already contained the four runtime routes that were previously missing:

| Retailer | Endpoint | Credits | Required request context |
|---|---|---:|---|
| BJ's | `/mc/bjs/pdp/zipcode/` | 2 | ZIP and store; URL or product ID |
| Costco | `/mc/costco/pdp/zipcode` | 4 | ZIP, store, fulfillment; URL or product ID |
| CVS | `/mc/cvs/pdp/zipcode` | 3 | URL, ZIP, store, fulfillment |
| Walgreens | `/mc/walgreens/pdp/zipcode` | 2 | ZIP, store, fulfillment; URL or product ID |

The normalized source CSV, runtime catalog, request adapter tests, and catalog reconciliation contract now agree on 20 endpoints. Tests fail if runtime routes diverge from the supplied endpoint source.

## Required Enrichment Order

1. Recheck the exact-context 30-day PDP cache.
2. Enqueue only uncached admitted products within an explicitly approved budget.
3. Persist raw PDP payloads and normalize the full useful field set.
4. Apply first-party seller governance before matching.
5. Extract governed supplement attributes, unit-price inputs, markdown evidence, and USP, NSF, and MSC certification evidence.
6. Create exact-spec and compatible-spec candidates only from governed products.
7. Use deterministic rules first and AI only for unresolved evidence.
8. Certify matches before competitive reporting publication.

## Automated Trust Checks

- Every raw object checksum must match its dataset artifact record.
- Successful and failed tasks must reconcile to the total task count.
- Distinct admitted products must reconcile to the PDP plan.
- Every admitted product must build a valid catalog-driven request.
- Planned credits must equal the sum of retailer endpoint credits.
- Runtime PDP endpoints must reconcile to the supplied source catalog.
- Product Pack fixtures must validate against the shared schema and referenced report blueprint.
- Known topical, pet, beverage, and tea noise must stay excluded.
- A valid oral supplement must stay admitted.

## Reproducible Evidence

- Audit script: `scripts/audit_spring_valley_search.py`
- Bounded audit result: `artifacts/spring-valley-search-audit/audit.json`
- Retailer summary: `artifacts/spring-valley-search-audit/retailer-summary.csv`
- Executable notebook: `artifacts/spring-valley-search-audit/spring_valley_search_audit.ipynb`
- Portable stakeholder report: `artifacts/spring-valley-search-audit/report.html`

The notebook code cells were executed top-to-bottom with Python 3. The portable report passed canonical artifact validation and structural packaging. Per-artifact Chromium interaction verification was unavailable because the installed headless browser exited during the verifier; the self-contained semantic report path remains included.

## Visualization Contract

The report uses one sorted horizontal comparison chart because the analytical question is retailer workload concentration, not trend or relationship. The chart is backed by the full retailer summary dataset, exposes task success and credits in its data view, uses a single-root palette, and is accompanied by exact retailer and field-quality tables.

## Decision Needed for the Next Phase

Paid PDP work requires a separate scope and budget approval. The current full uncached ceiling is 2,431 calls, 5,336 credits, and $10.67. A bounded validation tranche can be used first if lower execution risk is preferred.
