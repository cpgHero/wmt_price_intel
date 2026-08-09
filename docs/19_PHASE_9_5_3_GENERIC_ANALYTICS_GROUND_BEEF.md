# Phase 9.5.3 — Generic Analytics and Fresh Ground Beef

## Status

Implemented. This is the acceptance and operating record for the Phase 9.5.3 checkpoint.

## Outcome

The generic analytics runtime now reproduces the complete August 7, 2026 fresh-ground-beef
reference analysis from all 225,791 supplied rows. Product scope, validated retailer catalogs,
lean/fat ratios, package weights, production claims, premium tiers, comparison profiles, and
reporting caveats live in `product-packs/fresh_ground_beef.json`. No ground-beef category branch
exists in the normalizer, classifier, comparison engine, worker, or other generic runtime module.

The historical worker no longer materializes all source rows, normalized offers, and classified
offers at once. It now:

1. downloads each immutable CSV to a private temporary file while calculating SHA-256;
2. rejects the source before parsing if the checksum differs;
3. yields 5,000-row CSV batches and verifies the contracted final row count;
4. normalizes and classifies each unique offer once;
5. writes normalized and classified Parquet partitions incrementally;
6. retains only the lowest positive offers that can affect a configured comparison; and
7. uses a geographic grid to bound candidate stores before calculating exact Haversine distance.

The comparison reducer is driven only by Product Pack dimensions, metrics, constraints, brand
policy, geography, unknown handling, and retailer-aware availability policy. Existing strict,
compatible/wildcard, unit-normalized, and radius profiles retain their prior behavior.

## Source and package semantics

The supplied SERP observations remain authoritative for price, search presence, ZIP, store,
location, and collection time. The Product Pack requires a positive captured USD price but does
not overwrite that price during normalization.

The validated catalog contains:

| Retailer | Qualifying products | Qualifying rows | Qualifying ZIPs | Qualifying stores |
|---|---:|---:|---:|---:|
| Walmart | 36 | 71,859 | 3,823 | 4,251 |
| ALDI | 12 | 25,930 | 2,472 | 2,595 |
| Amazon | 38 | 11,065 | 2,066 | 0 |

ALDI variable-weight listings use validated expected package weights while retaining the August 7
captured package total. For example, product `17771077` remains $13.93 and its configured 2.25 lb
weight produces approximately $6.1911/lb.

Amazon search presence remains part of qualifying coverage, but profiles use explicit in-stock
observations for price matching. This distinction reproduces the reference coverage and prevents
an unavailable localized offer from becoming the selected competitive price.

## PDP validation ledger

Six Amazon PDP requests returned HTTP 200 and one attempt timed out. No 404 was generated. The
successful checks resolved ambiguous package/category semantics for the localized Ground Chuck,
80/20, organic 93/7, and 48 oz value-pack listings. PDP fields validated identity and package
semantics only; PDP prices and current availability did not replace historical SERP observations.

These calls were inside the product owner's approved development bank. Full-location regression
uses only the supplied files and makes no live MetricsCart request.

## Full-source golden evidence

| Assertion | Actual |
|---|---:|
| Source rows | 225,791 |
| Walmart qualifying ZIPs | 3,823 |
| ALDI exact matches | 9,049 |
| ALDI competitor-lower rate | 84.14189413% |
| Amazon exact matches | 6,713 |
| Walmart-lower rate vs. Amazon | 93.63920751% |
| ALDI 10-mile matches | 16,985 |
| Organic grass-fed 85/15 ALDI median gap | -$1.48/lb |

Every retailer scorecard and strict lean/weight/claim segment in the reference workbook also
reconciles exactly. The opt-in regression executes strict package, price-per-pound, variable-weight,
and 10-mile profiles through the production Product Pack loader, classifier, streaming reducer,
and comparison engine.

On the local acceptance environment, the measured full regression completed in 50.294 seconds
with peak resident memory of 425,164,800 bytes (about 405.5 MiB). The indexed radius implementation
replaced the prior unbounded all-store scan.

## Commands

```bash
RCI_GOLDEN_GROUND_BEEF_WALMART_CSV=/path/to/Ground_Beef___Walmart_All_Stores_20260807_051643.csv \
RCI_GOLDEN_GROUND_BEEF_ALDI_CSV=/path/to/Ground_Beef___Aldi_All_Stores_20260807_051606.csv \
RCI_GOLDEN_GROUND_BEEF_AMAZON_CSV=/path/to/ground_beef_amazon.csv \
uv run pytest packages/python/rci-analytics/tests/test_full_ground_beef_golden.py -q
```

```bash
uv run pytest packages/python/rci-analytics/tests/test_product_pack_abstraction.py -q
```

```bash
make check
```

## Railway operating gate

Production acceptance completed against Railway Postgres and the Railway bucket. The importer
registered manifest checksum
`baa44b8ee3fddf4d68e64ffb1c3c6234683641e71491a0e6a8aff940f4b7745a` exactly once with three raw
artifacts and 225,791 rows. The private-network integration suite passed all five Postgres tests:
queue leasing, shared rate limiting, immutable results, scheduler/email idempotency, and historical
input replay.

The successful production run reproduced the headline golden comparisons exactly:

| Profile | Matches | Benchmark lower | Competitor lower | Parity |
|---|---:|---:|---:|---:|
| ALDI strict | 9,049 | 1,435 | 7,614 | 0 |
| Amazon strict | 6,713 | 6,286 | 386 | 41 |
| ALDI 10-mile | 16,985 | 2,820 | 14,165 | 0 |

The run published 45 normalized Parquet partitions, 45 classified partitions, two match-detail
artifacts, and ready HTML, XLSX, leadership-email, and audit-ZIP artifacts. Result validation is
`ready_to_share`. Runtime `coverage.offers` and `coverage.in_scope_offers` count deduplicated
canonical offers; the qualifying-row table above intentionally counts source-row occurrences.
Both representations agree on distinct qualifying ZIP and store counts.

`ANALYSIS_HISTORICAL_REPLAY_ENABLED` was returned to `false` after acceptance so later historical
inputs cannot be claimed accidentally.

Phase 9.5.4 remains responsible for durable product identity and reusable PDP enrichment. This
checkpoint uses only the minimum PDP validations needed to establish the Product Pack golden.
