# Phase 9.9.4 — Cross-category certification and delivery parity

## Outcome

Certify the primary application across fresh ground beef, fresh shell eggs, fresh fluid milk,
fresh bananas, and fresh strawberries before Phase 10. Repair Product Details enrichment only
where the provider contract or missing identity evidence prevents a useful product experience,
then bring every delivery surface forward from the same immutable publication.

This phase does not change Search-derived prices, availability, stores, ZIP codes, match outcomes,
or deterministic calculations. Search remains authoritative for those facts. PDP evidence may add
identity, package attributes, descriptions, identifiers, images, and other referential detail.

## Corrected MetricsCart PDP contracts

Live production-key probes on August 10, 2026 verified these request shapes:

| Retailer | Path | Required context | Verified result |
| --- | --- | --- | --- |
| ALDI | `/mc/new_aldi/pdp/zipcode/` | `product_id`, `zipcode`, `store`, `fulfillment_type=pickup` | Product `17499083`, ZIP `71111`, requested store `475-107`: HTTP 200 |
| Walmart | `/mc/walmart/product/zipcode/` | `product_id`, `zipcode`, `store`, `fulfillment_type=pickup` | Product `15136790`, ZIP `03038`, store `1753`: HTTP 200 |
| Amazon Same Day | `/mc/amazon/pdp/zipcode/` | product identity plus supported ZIP context | Existing ground-beef jobs: 29 HTTP 200 |

The ALDI response may expose a provider-internal `retailer_store_id` that differs from the requested
ALDI store code. The immutable snapshot must retain both: requested store/ZIP/fulfillment in
`request_context`, and the response value in normalized PDP extras. The response value must never
replace the Search observation's store identity.

The previous ground-beef run used no-slash ALDI and Walmart paths. Its latest product-level state
was 11 ALDI HTTP 404s, 29 Walmart HTTP 404s, and 29 Amazon HTTP 200s. Because the same ALDI and
Walmart product/location examples now return HTTP 200 on the slash-terminated paths, those failures
are classified as adapter-contract failures rather than unavailable retailer pages.

## Paid-call and selection policy

1. Enrichment is restricted to products admitted into governed analysis relationships. Search
   noise and unmatched result rows are excluded.
2. A PDP request requires a positive Search price and uses a store/ZIP where that exact product was
   observed. Missing- and zero-price rows cannot supply a request context.
3. One representative request is made per retailer product. If the same retailer product has
   distinct positive Search prices, one representative location per price state is allowed.
4. Existing successful unexpired snapshots are reused. Successful Amazon ground-beef PDPs are not
   repeated.
5. Status 200 and 404 consume the configured retailer credits; all paid work is created under a
   hard run ceiling and uses the shared multi-replica rate limiter.
6. The two contract probes consumed three credits. The corrected positive-price gate reduced the
   ground-beef repair from the original 69-credit estimate to 65 credits: 11 ALDI calls at one
   credit and 27 Walmart calls at two credits.
7. Additional category calls require a read-only estimate first. The 1,000-credit development bank
   remains the default ceiling unless the user explicitly approves a category exception. The full
   high-cardinality milk plan was approved after its 1,405-credit pre-cache estimate was disclosed.

## Certification sequence

### Gate A — Adapter and planner correctness

- Pin the verified trailing-slash ALDI and Walmart paths in the retailer-neutral PDP catalog.
- Preserve identifiers, ZIP codes, and store numbers as strings, including leading zeros.
- Require `fulfillment_type=pickup` for ALDI and Walmart.
- Reject missing and zero Search prices as PDP representative locations.
- Verify billing, raw-response immutability, normalization, request provenance, deduplication, and
  price-variant behavior in tests.

Exit: contracts, `rci-products`, and handoff validation pass.

### Gate B — Bounded ground-beef recovery

- Deploy the corrected worker before creating recovery jobs.
- Run read-only estimates for ALDI and Walmart.
- Enqueue only the analysis-admitted, positive-price candidates under a 65-credit ceiling.
- Wait for the durable queue to reach a terminal state and reconcile planned versus actual credits,
  HTTP outcomes, cache hits, and product identity/image coverage.
- Do not retry the already-successful Amazon requests.

Exit: no recovery job uses the obsolete path; every request has auditable Search context; spending
does not exceed the ceiling.

### Gate C — Five-category application certification

For ground beef, eggs, milk, bananas, and strawberries:

- validate competitor focus, named retailer labels, comparison lens, one-to-one relationship state,
  and staged match-change behavior;
- reconcile Overview, Price, Segments, Products, Geography, Assortment, Opportunities, Quality, and
  Match Review against the same relationship IDs and denominators;
- verify pair-detail deep links, store-level evidence, useful empty states, product imagery fallback,
  and no PDP-derived overwrite of Search price/location facts;
- compare category-defining metrics with the full-source golden benchmarks; and
- visually check desktop and narrow-screen usability in the primary application.

PDP gaps that do not affect product identity or decision integrity remain explicit missing states;
they do not justify broad collection.

### Gate D — Delivery parity

- Rebuild publication context only after PDP jobs finish.
- Project the canonical ReportView/publication into the application, shareable report, HTML,
  leadership email, and workbook without renderer recalculation.
- Increment renderer versions and create new immutable artifacts; retain prior artifacts for audit.
- Programmatically reconcile retailer, lens, relationship, product outcome, price gap, geography,
  readiness, and match status across surfaces.
- Perform a final visual review of HTML and shareable delivery after the primary application passes.

Exit: no delivery surface contains obsolete product cards, maps, labels, or outcome values.

## Acceptance tests

1. ALDI and Walmart adapters emit the exact verified paths and parameters.
2. ALDI leading-zero product IDs and ZIP codes remain strings.
3. Requested store context survives even when the provider response returns another store identifier.
4. Search noise, zero prices, and missing prices create no PDP candidates.
5. Repeated locations at one price create one request; distinct positive prices create one request
   per price state.
6. A failed old-path snapshot cannot suppress a corrected-path recovery job.
7. Ground-beef recovery has exactly 11 ALDI and 27 Walmart paid calls; Amazon has zero new calls.
8. Product enrichment changes identity/presentation fields only, never Search price or location.
9. Five full-source category goldens pass without category-specific core branches.
10. Application and regenerated deliveries agree on all decision values and relationship states.

## Verification commands

```bash
.venv/bin/ruff check packages/python/rci-products apps/worker
.venv/bin/pytest packages/python/rci-products/tests -q
.venv/bin/python scripts/validate_handoff.py
pnpm --filter @rci/contracts check
pnpm --filter @rci/web typecheck
pnpm --filter @rci/web test
pnpm --filter @rci/web build
.venv/bin/pytest \
  packages/python/rci-analytics/tests/test_full_ground_beef_golden.py \
  packages/python/rci-analytics/tests/test_full_egg_golden.py \
  packages/python/rci-analytics/tests/test_full_milk_golden.py \
  packages/python/rci-analytics/tests/test_full_banana_golden.py \
  packages/python/rci-analytics/tests/test_full_strawberry_golden.py -q
```

## Deployment order

1. Record current service deployment IDs and database backup state.
2. Deploy the corrected catalog/planner and confirm worker health.
3. Run bounded ground-beef recovery and reconcile its terminal ledger.
4. Rebuild ground-beef publication context and certify the primary application.
5. Run read-only estimates for the other four categories; use cached PDP evidence first and approve
   only analysis-required gaps within the remaining credit bank.
6. Rebuild and certify the five primary application publications.
7. Regenerate versioned delivery artifacts and certify parity.

## Executed recovery ledger

The production-key recovery and cross-category plans use only governed product relationships and
positive Search-price observations. Search remains the authority for price and location.

| Category | Planned contexts | Cache hits | Paid jobs | Actual credits | Terminal result | Retailer scope |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Ground beef repair | 38 | 0 | 38 | 65 | 38 succeeded | ALDI, Walmart; Amazon reused |
| Milk | 710 | 75 | 635 | 1,255 | 635 succeeded | ALDI, Amazon Same Day, Walmart |
| Bananas | 33 | 12 | 21 | 38 | 21 succeeded | ALDI, Amazon Same Day, Walmart |
| Strawberries | 33 | 23 | 10 | 16 | 10 succeeded | ALDI, Amazon Same Day, Walmart |
| Eggs | 244 | 6 | 238 | 470 | 234 succeeded; 4 HTTP 404 | ALDI, Amazon Same Day, Walmart |

The corrected ground-beef jobs completed 38 of 38 with HTTP 200. Together with the three-credit
contract probes, the ground-beef validation consumed 68 credits. The four cross-category runs
consumed 1,779 credits, or $3.558 at $0.002 per credit. Including ground-beef repair and probes, the
Phase 9.9.4 Product Details validation consumed 1,847 credits, or $3.694. Every milk, banana, and
strawberry job succeeded. Egg certification retained four explicit unavailable-product states
rather than hiding or substituting them.

The cross-category load test was temporarily scaled from one to three, eight, and twelve Railway
worker replicas. At twelve replicas, MetricsCart returned six non-billable Walmart HTTP 429s: four
during milk and two during eggs. The shared cooldown correctly paused every replica and all six jobs
subsequently succeeded, but the event exposed a fixed-window boundary burst:
three permits near the end of one second and three near the start of the next can violate a provider
rolling window. Migration `0020_provider_permit_pacing` adds a shared `next_permit_at` timestamp.
Permits are now globally spaced at the stricter per-second/per-minute interval with two-percent
headroom, while the existing database cooldown remains authoritative across all replicas.

MetricsCart also returned three non-billable HTTP 500 responses: two ALDI milk attempts and one
ALDI banana attempt. Durable retries succeeded. Those transient responses consumed no credits and
did not create missing PDP states.

### Replicable terminal HTTP 404s

All four failures use a positive-price Search observation for the exact item, ZIP, and store shown.
The API key is intentionally omitted from these diagnostic URLs.

| Retailer | Product | ZIP | Store | Request URL |
| --- | --- | --- | --- | --- |
| ALDI | `25928369` | `01020` | `473-022` | `https://api.metricscart.com/mc/new_aldi/pdp/zipcode/?product_id=25928369&zipcode=01020&store=473-022&fulfillment_type=pickup` |
| Walmart | `142862696` | `64154` | `2857` | `https://api.metricscart.com/mc/walmart/product/zipcode/?product_id=142862696&zipcode=64154&store=2857&fulfillment_type=pickup` |
| Walmart | `662711730` | `69361` | `867` | `https://api.metricscart.com/mc/walmart/product/zipcode/?product_id=662711730&zipcode=69361&store=867&fulfillment_type=pickup` |
| Walmart | `958047526` | `45005` | `3784` | `https://api.metricscart.com/mc/walmart/product/zipcode/?product_id=958047526&zipcode=45005&store=3784&fulfillment_type=pickup` |

Egg estimates also identified valid-looking catalog entries for H-E-B and Safeway. They are excluded
from paid certification until their current exact request contracts are verified. Other egg
retailers remain explicit unsupported or missing-parameter states rather than silently entering the
queue.

## PDP refresh cadence policy

High-cardinality categories such as milk legitimately contain local brands, pack variants, and
regional assortment differences. The initial governed identity build may therefore require many
PDP calls. Subsequent collections should separate the two cadences:

- Search price and availability remain collection-cadence, store-specific evidence.
- New products and products whose admitted identity/package signals materially changed receive PDP
  enrichment first.
- Stable enriched products use a configurable weekly or monthly PDP freshness window instead of
  being recollected on every Search run.
- A user-triggered identity refresh may override the normal PDP freshness window, subject to an
  explicit credit estimate and ceiling.
- The cache key continues to include retailer, product, supported ZIP/store context, fulfillment,
  and provider-contract version so a contract correction cannot be hidden by an old failure.

## Milk comparison hierarchy

Regional brands and local assortment breadth do not relax price-match cardinality. The reporting
contract has three distinct levels:

1. **Product relationship:** one Walmart product to one competitor product within an active
   comparison lens. Store-level price facts, evidence downloads, and user match governance remain
   one-to-one and auditable.
2. **Comparable cohort:** Product Pack attributes roll products into retailer-neutral milk cohorts,
   including package volume, fat level, organic status, lactose-free status, and other governed
   specifications. Multiple products may contribute to a cohort summary without becoming a
   many-to-many product match.
3. **Assortment rollup:** retailer and geography views summarize cohort coverage, local-brand
   breadth, whitespace, availability, price leadership, and volatility. Whitespace is a review
   signal, not an assumed substitute.

When one product has several plausible counterparts, the engine ranks candidates under each lens.
It may select one deterministic best pair or stage the ambiguity for review, but it must not count
the cross-product of candidates as independent price matches. This keeps category-level reporting
useful for Dairy leadership without compromising item-level price integrity.

## Deferred

- Phase 10 dynamic collection geography and collection wizard work;
- onboarding additional retailer adapters beyond the current category certification needs;
- RBAC and role-based tab visibility; and
- automatic price actions or prescriptive retailer execution.

## Blocking questions

None. The verified request examples, production failure ledger, historical source evidence, Product
Packs, and existing golden benchmarks are sufficient to execute this phase.
