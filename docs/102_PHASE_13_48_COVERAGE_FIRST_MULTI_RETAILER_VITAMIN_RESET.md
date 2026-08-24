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

### Retailer-wide brand governance

Retailer Packs now support exact, versioned `verified_private_labels` when a confirmed
retailer-owned brand has not yet reached the next shared Brand Foundation release. The
resolver remains fail-closed, retailer-scoped, and exact; these entries only classify a
brand lane and never prove product compatibility. Governed coverage now includes Amazon
Elements and Solimo, Berkley Jensen and Wellsley Farms, Kirkland Signature, CVS Health,
Meijer, Member's Mark, and Walgreens/Free & Pure. Existing Target and Kroger private
labels continue to resolve from Brand Foundation 2.0.0.

### Certification boundary

Vitamins & Supplements Product Pack 1.2.2 keeps active ingredient/formulation, strength and unit, dosage form, release profile, and life stage as fail-closed hard blockers. It adds governed title/PDP formula-family extraction, preserves named release and audience conflicts, and permits `Standard` release and `General` audience only through explicit Product Pack absence policies. Brand is descriptive, so a retailer private label can match Spring Valley when governed specifications agree. Package count remains a price-basis attribute rather than a substitute for product identity.

The second retained-data shadow found that scalar ingredient evidence could still overstate
complex-formula equivalence, such as a blood-sugar support blend versus a different
chromium-containing formula. Product Pack 1.2.2 therefore disables deterministic automatic
approval while formula signatures are calibrated against a reviewed benchmark set. Exact-item
and exact-specification proposals remain visible for AI/human review, but none can become final
without certification. This is an intentional temporary trust gate, not a permanent requirement
for manual review.

Equivalent-product and broader relationships also require human certification. Unknown or
conflicting hard blockers never auto-approve.

### Collection-query retrieval evidence

The live Search bridge now preserves the exact request keyword on every normalized Search row.
The listing accumulator collapses those values into product-level retrieval contexts. Product
Packs may require a shared context when both products have it, which restores high recall within
the owner-defined family without asserting comparability. Query context affects candidate
retrieval and ordering only; it cannot override a hard conflict, create attribute evidence, or
certify a match.

### Bounded PDP brand evidence

PDP brand resolution now uses only the structured PDP brand and product name. Retailer category
breadcrumbs and long descriptions are excluded from the brand-resolution surface. This prevents
rows such as `Meijer > Nature Made Vitamin C` from being mislabeled as Meijer private label while
still allowing a genuine Meijer-branded product to resolve from explicit brand/name evidence.

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

## Retained-evidence shadow findings

The first read-only shadow used 2,187 retained PDP snapshots and all successful Spring
Valley Search evidence. It generated 11,429 unresolved cases. That queue was correctly
blocked and was never imported: it proved that candidate recall had expanded across all
nine competitors, but also exposed unacceptable manual-review volume and missing critical
attribute evidence. It also confirmed that 199 of the 322 governed Walmart anchors were
not positively observed in the one-market pilot; that is a collection-coverage issue, not
proof of national unavailability.

The repair after that gate failure was Product Pack 1.2.1 plus the versioned Retailer Pack
brand coverage above. Candidate retrieval now requires either the same governed formula
family or materially stronger lexical evidence, retains at most 24 candidates per
benchmark/retailer, and preserves three candidates per brand lane.

The second read-only shadow produced 239 cases: 223 unresolved, three equivalent-product
candidates, and 13 automatic exact-specification proposals. It materially repaired precision,
but failed both the recall and zero-false-positive gates. Only 4–57 candidate pairs survived per
retailer, 87–119 of the 123 observed Walmart anchors lacked any retained candidate depending on
retailer, and 199 catalog anchors still lacked a positive-price observation. Semantic inspection
also found the complex-formula false positive above and found retailer breadcrumb contamination
in brand evidence. The queue was never imported.

Product Pack 1.2.2, bounded PDP brand resolution, and shared-query-context retrieval are the
response to that failed gate. The third shadow must show zero automatic approvals, no known
audience/formula/strength/form/release conflicts among positive proposals, materially improved
anchor coverage, accurate private-label attribution, and an operationally bounded case count.
Only after those gates pass will the owner receive a priced, early-stopping multi-market Search
recovery plan for the 199 unobserved catalog anchors and broader competitor discovery.
