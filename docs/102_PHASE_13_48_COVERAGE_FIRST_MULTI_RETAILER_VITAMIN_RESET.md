# Phase 13.48 — Coverage-First Multi-Retailer Vitamin Reset

## Decision

The Spring Valley matching workflow must account for every governed Walmart anchor against every configured competitor retailer before candidate precision is evaluated. Target is not a special case. The same retrieval, brand-lane, seller-governance, evidence, and coverage rules apply to Amazon Same Day, BJ's, Costco, CVS, Kroger, Meijer, Sam's Club, Target, and Walgreens.

The 322-product Spring Valley catalog is the benchmark universe. Search observation is evidence that a product was seen at a sampled location and positive price; non-observation at one market is not evidence that a catalog product is unavailable nationally. Product identity discovery is therefore catalog-wide. Geographic applicability remains a later, separate price-comparison step.

## Defects addressed

The previous queue was unsafe as a completeness measure:

- it represented 56 of 322 Walmart catalog anchors;
- its lexical top-five retrieval could crowd out retailer private labels and other valid brand lanes;
- geography was applied before product-identity candidate discovery even though the pilot used one sampled market;
- numeric strength evidence was weakened by generic token handling;
- configured benchmark products not observed in Search were absent rather than explicitly accounted for; and
- a small certified set could be mistaken for complete assortment coverage.

The existing 203-case Spring Valley queue remains immutable audit history and is not a release candidate for reporting.

## Implemented generic capabilities

### Coverage ledger

Every evidence profile now includes a benchmark-product × competitor-retailer coverage ledger. Each cell is classified as:

- `benchmark_not_observed`: the governed Walmart catalog anchor lacks a positive-price Search observation in the supplied evidence;
- `candidate_found`: at least one candidate survived deterministic conflict and retrieval gates; or
- `no_candidate_after_retrieval`: the Walmart anchor was observed but no competitor candidate survived.

The ledger reports catalog, observed, candidate-covered, and uncovered counts by retailer. It also reports the competitor assortment admitted by first-party seller governance and its private-label, regional, national, and unclassified brand composition. This prevents absent retailers or missing private-label lanes from disappearing silently.

### Structured high-recall retrieval

The generic matching engine now supports a Product-Pack-configured `structured_high_recall` retrieval mode. It:

1. excludes known hard conflicts before ranking;
2. preserves numeric strength tokens;
3. rewards governed structured-attribute agreement;
4. combines structured evidence with conservative title-token similarity;
5. preserves a minimum number of candidates from distinct competitor brand lanes before filling the remaining ranked capacity; and
6. retains unknown hard-blocker candidates for PDP/image evidence review without making the unknown certifiable.

The capability contains no vitamin-specific or retailer-specific branch. Product Pack configuration selects attributes, thresholds, numeric handling, lane diversity, candidate limits, and certification requirements.

### Certification boundary

Vitamins & Supplements Product Pack 1.2.0 keeps active ingredient/formulation, strength and unit, dosage form, release profile, and life stage as fail-closed hard blockers. Brand is descriptive, so a retailer private label can match Spring Valley when governed specifications agree. Package count remains a price-basis attribute rather than a substitute for product identity.

The pack authorizes deterministic automatic approval only for:

- a verified shared item identifier with no critical contradiction; or
- an exact-specification relationship where every critical attribute is known and compatible.

Equivalent-product and broader relationships still require human certification. Unknown or conflicting hard blockers never auto-approve.

## Collection implication

The matching reset does not infer national availability from the catalog. It creates a measured coverage problem:

1. retain all 322 Spring Valley anchors in the catalog ledger;
2. reuse Search and PDP evidence that remains within its governed freshness window;
3. use exact-title Walmart recovery Search for catalog anchors missing from the pilot;
4. expand Walmart recovery across a small, diverse, deterministic store panel with early stopping when an anchor is observed;
5. expand competitor keyword Search across diverse markets rather than adding a Kroger-only or Target-only exception;
6. record every retailer × keyword × market outcome, including HTTP failures and zero-result responses; and
7. rerun the coverage ledger before paid matching or certification.

No paid Search, PDP, or AI call is authorized by this phase document alone. The administrator must receive an exact task count, credit exposure, dollar ceiling, early-stop rules, and retry policy before launch.

## Release gates

The new queue may replace the quarantined Spring Valley queue only when all gates pass:

1. all 322 benchmark anchors appear in the coverage ledger for all nine competitors;
2. every configured retailer has Search evidence or an explicit collection limitation;
3. first-party seller governance is applied before assortment and candidate metrics;
4. private-label and non-private-label candidate lanes are visible by retailer;
5. known life-stage, ingredient, strength, unit, form, and release conflicts produce zero certifiable relationships;
6. a reviewed benchmark set demonstrates acceptable candidate recall without material precision collapse;
7. automatic approvals contain complete deterministic evidence and pass a zero-false-positive audit;
8. profile, queue, Product Pack, and source checksums reconcile; and
9. production import remains a separate explicit action after shadow results are accepted.

## Verification

Implementation verification includes Product Pack and evidence-profile schema validation, deterministic unit tests for brand-lane retention and numeric strength ranking, coverage-ledger reconciliation tests, Python lint/type/tests, TypeScript contract generation, and a retained-evidence shadow build. The read-only shadow builder is included in the API image; queue mutation still requires its separate explicit import flag. Deployment and paid collection are deliberately separate gates.
