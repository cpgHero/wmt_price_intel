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

Vitamins & Supplements Product Pack 1.2.3 keeps active ingredient/formulation, strength and unit, dosage form, release profile, and life stage as fail-closed hard blockers. It adds governed title/PDP formula-family extraction, preserves named release and audience conflicts, and permits `Standard` release and `General` audience only through explicit Product Pack absence policies. Brand is descriptive, so a retailer private label can match Spring Valley when governed specifications agree. Package count remains a price-basis attribute rather than a substitute for product identity.

The second retained-data shadow found that scalar ingredient evidence could still overstate
complex-formula equivalence, such as a blood-sugar support blend versus a different
chromium-containing formula. Product Pack 1.2.3 therefore disables deterministic automatic
approval while formula signatures are calibrated against a reviewed benchmark set. Exact-item
and exact-specification proposals remain visible for AI/human review, but none can become final
without certification. This is an intentional temporary trust gate, not a permanent requirement
for manual review.

Equivalent-product and broader relationships also require human certification. Unknown or
conflicting hard blockers never auto-approve.

### Collection-query retrieval evidence

The live Search bridge now preserves the exact request keyword on every normalized Search row.
The listing accumulator collapses those values into product-level retrieval contexts. Product
Packs may prefer or require shared context. Product Pack 1.2.3 uses it as a preference, not a
requirement, because the third shadow proved that exact shared-keyword gating hid valid
cross-query candidates. Query context affects candidate
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

`scripts/plan_spring_valley_location_panel.py` provides a read-only, reproducible location-master
diagnostic. It reports active and collection-eligible rows by retailer, finds the nearest physical
competitor stores within five miles of each Walmart location, and constructs a greedy minimum
Walmart-anchor panel that covers the configured physical competitors. A returned location is not
authorized for collection merely because it is geographically close; its provider-safe store ID,
ZIP, retailer status, and collection-eligibility result must pass the normal collection preflight.

The generic radius resolver also supports an optional
`maximum_locations_per_retailer_per_primary` control. When configured, it deterministically selects
the nearest N eligible stores for each competitor retailer around every selected primary-retailer
location. The cap is independent by retailer, so a dense CVS or Kroger footprint cannot crowd out
BJ's, Costco, Meijer, Sam's Club, Target, or Walgreens. Omitting the control preserves the existing
all-stores-within-radius behavior. The collection builder exposes the control explicitly and records
it in the immutable geography request and resolution snapshot.

The production location-master diagnostic found that Walmart store 5767 in Fishers, Indiana
(ZIP 46038) has at least one eligible location from all eight physical competitor retailers within
five miles; Amazon Same Day uses the Walmart ZIP. Without a per-retailer cap, that anchor expands to
34 physical competitor locations and would collect materially more evidence than the owner's
one-location-per-retailer discovery objective. With N=1, the proposed first recovery panel contains
one Walmart location, one Amazon ZIP, and the nearest eligible BJ's, Costco, CVS, Kroger, Meijer,
Sam's Club, Target, and Walgreens location. Provider preflight and the collection cost ceiling remain
mandatory before launch.

For the 85-keyword catalog, the N=1 first panel is 850 Search calls and 1,615 provider credits
($3.23). A separate exact-title Walmart recovery for the 199 currently unobserved anchors adds at
most 199 calls and credits ($0.398), for a disclosed first-stage ceiling of 1,049 calls, 1,814
credits, and $3.628. These are ceilings, not authorization. No paid call is launched until the owner
approves the staged budget.

The owner approved the $3.63 first-stage ceiling on August 24, 2026. Run
`016e05c8-119b-4580-be1d-e7609fdd3621` launched the 850-call panel with a hard 1,615-credit
budget and PDP enrichment disabled. Its single-call retailer availability gates passed promptly
for eight retailers. Retryable Costco HTTP 429 and Meijer HTTP 500 preflights exposed a generic
queue-order defect: released bulk tasks could sort ahead of eligible retrying preflights. Durable
claim order now prioritizes eligible preflight tasks before normal priority, while retaining
`FOR UPDATE SKIP LOCKED`, leases, retry limits, and retailer gates. This is an execution-order
repair only; it does not bypass a gate or change the approved credit ceiling.

The completed Search recovery used three immutable title-based runs plus one bounded product-ID
diagnostic. It spent 1,803 credits ($3.606) under the $3.628 ceiling and recovered 248 of the 322
governed Walmart anchors (77.02%). The remaining 74 anchors are explicit catalog-coverage gaps;
the product-ID diagnostic failed closed and the Sacramento second-market title recovery added only
one anchor, so further blind geographic expansion was rejected as low-value paid work. Across all
successful Search evidence, 2,553 distinct admitted products require cache-aware PDP qualification.

Product Details run `0e5ac06f-d372-42a8-9130-13415a3b5570` is the owner-approved enrichment run.
It completed 2,553 jobs with 2,284 successful normalized products and 269 terminal failures. It
consumed 5,417 credits ($10.834) under the 7,500-credit ($15.00) hard ceiling. It reused the
30-day cache contract and enriched one representative observed context per distinct admitted
product. The audit reconciled snapshots, normalized rows, seller governance, checksums, and
credits. Amazon, Target, and Walmart known third-party offers were excluded before the read-only
matching shadow; blank seller evidence remains explicitly unverified rather than assumed 1P.

The live run also exposed a generic concurrency defect: a worker waited for the slowest request in
each claimed batch before refilling. Product Details workers now retain unfinished leased tasks,
wait only for the next completion, and refill the freed capacity from the existing retailer-balanced
`SKIP LOCKED` claim order. Graceful shutdown finishes already-leased calls before closing the
provider transport. This changes throughput only; retailer-scoped rate limits, shared cooldowns,
leases, retries, cancellation, idempotency, immutable responses, and the run credit ceiling remain
authoritative.

The scaled recovery then exposed synchronized HTTP 429 responses across BJ's, Costco, Kroger,
Meijer, and Walmart PDP lanes. The provider was enforcing an account-wide burst boundary in
addition to the documented retailer/type limits. Product Details now acquires a shared two-per-second
and 120-per-minute account permit before the retailer permit. A 429 pauses both scopes. This keeps
multi-replica throughput bounded, prevents nonbillable cooldown attempts from consuming a job's
retry allowance, and leaves completed 200/404 evidence and the 7,500-credit ceiling unchanged.

The first operational transient requeue also exposed an attempt-ledger repair defect. The manual
repair reset a job counter even though its immutable attempt-one snapshot remained present, so the
database uniqueness constraint correctly rejected a second attempt-one record. Recovery now restores
affected counters from the maximum retained snapshot attempt before retrying. The worker also isolates
and logs an individual durable-record failure rather than terminating the process; the lease remains
recoverable by the queue. Existing snapshots are never overwritten or deleted, billable 404s are not
requeued, and the run credit ceiling is unchanged.

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

Product Pack 1.2.2, bounded PDP brand resolution, and shared-query-context retrieval were the
response to that failed gate. The third shadow produced 116 cases with zero automatic approvals
and corrected the Meijer breadcrumb contamination, but exact shared-context gating was too
restrictive: 106–122 observed anchors per retailer lacked a candidate. It was never imported.

Product Pack 1.2.3 changes context overlap from required to preferred, retains the zero-auto-
approval boundary, and excludes obvious non-oral Search noise such as wipes, patches, and drink
mixes. The fourth shadow must show zero automatic approvals, no known audience/formula/strength/
form/release conflicts among positive proposals, materially improved anchor coverage, accurate
private-label attribution, and an operationally bounded case count. Only after those gates pass
will the owner receive a priced, early-stopping multi-market Search recovery plan for the 199
unobserved catalog anchors and broader competitor discovery.

The fourth retained-evidence shadow was evaluated independently for all nine competitors after
the combined build exceeded the API replica's memory limit. The retailer-scoped builds produced
240 cases: 230 unresolved, seven exact-specification candidates, three equivalent-product
candidates, and zero automatic approvals. Semantic inspection of all ten positive proposals found
plausible strength, form, release, and audience relationships; the corrected Target lane included
governed up & up private-label products rather than silently losing that assortment.

The fourth shadow nevertheless failed recall. Depending on retailer, 88–119 of the 123 observed
Spring Valley anchors had no retained candidate. The competitor critical-attribute completion
rate ranged from 10.7% to 55.9%, and 199 of 322 governed Walmart catalog anchors remained
unobserved at a positive price. No fourth-shadow queue was imported. The evidence supports a
bounded multi-market Search recovery plus cache-aware PDP enrichment; it does not support more AI
review of the current one-market candidate set.
