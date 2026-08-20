# Phase 13.26 — Egg Reporting Acceptance and Trust Audit

## Status

Core relationship-preservation, terminal-exclusion, and semantic-audit changes
were deployed and release-gate verified on August 20, 2026. The platform owner
has completed all 185 review cases. A first immutable replay exposed a second
legacy readiness dependency before publication; the corrected generation-two
replay and production reporting acceptance remain pending.

## Purpose

This phase establishes a fail-closed acceptance boundary between Matching v2
certification and Competitive Intelligence reporting. It corrects a critical
lineage defect in which a certified product relationship could disappear from
the report when its two products had no positive-price observation in the same
ZIP, even though the reporting layer was designed to compare physical stores at
1, 3, or 5 miles.

Product identity and local price evidence are now treated as separate facts:

- Matching v2 certification determines whether two product identities form a
  governed relationship and which comparison bases may use it.
- Search observations determine product price and observed location footprint.
- The location master determines physical store coordinates and administrative
  geography.
- The selected 1, 3, or 5 mile radius determines whether physical-store price
  evidence is locally comparable.
- Amazon Same Day retains its explicit same-delivery-ZIP service-area rule; it
  is never represented as a physical store.

## Defect found in the governed Egg release

The operational Egg queue contained 185 cases: 183 certified comparable, one
certified not comparable, and one case awaiting its final human disposition.
The published report retained
only 108 relationship candidates because the worker created presentation
relationships from exact-ZIP `MatchRecord` rows instead of from the certified
gold set itself. Sam's Club, ShopRite, and Trader Joe's therefore disappeared
entirely despite having certified comparable relationships.

The loss occurred before radius-native scoring. It was not evidence that these
retailers lacked governed relationships, and it could not be repaired safely in
the browser.

## Implementation

### Certified relationship projection

For a Matching v2 replay, the worker now starts with every certified-comparable
gold-set decision and creates one deterministic pair-level relationship. It
then creates the eligible comparison-basis candidates independently of
exact-ZIP price overlap. Search data supplies identity, imagery, attributes,
and the Walmart observed-store footprint where available. Existing exact-ZIP
price metrics may enrich the presentation row, but their absence cannot remove
the relationship.

The worker reconciles the retained pair-level total and every retailer subtotal
to the immutable release coverage contract. A missing or invented relationship
fails the analysis before publication.

### Assortment and cohort continuity

Assortment coverage now incorporates the certified relationship ledger even
when no exact-ZIP `MatchRecord` exists. This prevents a certified pair from
being mislabeled as benchmark-exclusive or competitor whitespace.

Cohort Scorecards can derive governed Product Pack cohort membership from the
certified candidate attributes when a legacy exact-location price segment row
does not exist. Only configured Product Pack cohort dimensions participate;
brand or other incidental attributes are not silently promoted into a cohort
definition.

### Publication readiness

The report renderer now recognizes a Matching v2 gold-set release as governed
match authority. Certified relationship totals and retailer subtotals must
reconcile to the presentation relationship ledger. A mismatch is a blocking
readiness defect rather than a nonblocking warning.

Publication-time Competitive Intelligence materialization refuses any report
with a blocking readiness reason.

AnalysisResult validation also treats a complete Matching v2 certification as
the product-identity authority. It no longer requires every retailer to have a
legacy exact-ZIP aggregate before radius-native reporting can proceed. This
exception is deliberately narrow and fail closed: the release must explicitly
account for every queue case as certified or human-reviewed insufficient
evidence, contain zero pending cases overall and per retailer, cover the exact
configured competitor set, declare selection complete, and disable automatic
fallback. At least one deterministic comparison fact is still required, and
the downstream six-document semantic audit remains mandatory.

### Six-document semantic release audit

Every comparison basis must produce one global immutable portfolio document at
1, 3, and 5 miles. The semantic audit validates more than JSON shape:

- one analysis, benchmark retailer, competitor set, and explicit geography
  policy across all documents;
- complete comparison-basis × radius coverage;
- benchmark denominator = scored + unscored;
- scored = leader + tied + at-risk + losing;
- every displayed rate reconciles to its governed numerator and denominator;
- product and relationship rows add to the parent scorecard and use the
  decision-evidence ordering shown in the UI;
- Assortment and price scorecards share the same governed price-evidence
  summary;
- product, relationship, and benchmark-denominator scope stays stable when the
  radius changes;
- scored evidence cannot decrease, and unscored evidence cannot increase, as a
  physical-store radius expands from 1 to 3 to 5 miles.

Semantic errors block the release. Honest evidence limitations, such as a
certified relationship with no scorable nearby product-location, remain
explicit warnings.

## Terminal insufficient-evidence boundary

The platform owner completed the final Kroger case with a deliberate
`insufficient_evidence` disposition: count, size, organic status, and shell
color align, but one product lacks the housing-method evidence required by the
Egg Product Pack. The platform must not invent that attribute, force a match,
or misstate the case as abandoned work.

The immutable gold-set release therefore preserves final human
insufficient-evidence dispositions in a separate `exclusions` ledger. They
remain outside both comparable and not-comparable metrics, change the release
checksum, retain reviewer/rationale/evidence provenance, and appear as an
explicit nonblocking report limitation. Only a case with no final human outcome
blocks publication as pending review. Release creation reconciles the exclusion
ledger to the current queue in the same database transaction so a decision
change cannot race the immutable snapshot.

## Focused verification

Fifty-seven focused Python tests pass across the worker, analytics, report
renderer, portfolio API, and semantic release audit. They include regressions
for a certified Sam's Club-style relationship whose Walmart and competitor
Search observations occur in different ZIPs, assortment continuity, derived
cohort membership, publication blocking on relationship loss, complete
comparison-basis/radius matrices, formula reconciliation, rollups, ordering,
and monotonic radius behavior.

No MetricsCart or OpenAI calls are required by this phase. No source data, PDP
evidence, certification history, publication, or audit lineage is deleted.

GitHub Actions run `32427778056` passed contracts, formatting, lint, type
checking, the Postgres migration upgrade/downgrade/re-upgrade cycle, 606 Python
tests with 13 environment-gated local fixtures, 68 web and contract tests, 13
browser tests, the production Next.js build, and the web, API, worker, and
scheduler container builds. Railway API and worker services were verified to
be running commit `04aab97`, including the new relationship projection and
semantic release audit.

The first governed replay used immutable release
`3c967ecc-17fd-4bad-a749-c223519723d0` and produced analysis
`fresh_shell_eggs-0474c5c1-3949-4623-ac12-7aa76f838bcc-match-v2-3c967ecc`.
It retained all 183 certified-comparable relationships plus the certified
not-comparable decision and final insufficient-evidence exclusion, but was not
promoted: AnalysisResult validation still expected legacy exact-ZIP comparison
facts for Sam's Club and Trader Joe's. It therefore created no portfolio
materializations. The failed acceptance artifact remains immutable audit
evidence and is not treated as an approved report.

The readiness correction has focused regression coverage proving that a
complete Matching v2 release can supply identity completeness when a retailer
lacks a legacy exact-ZIP row, while an older or partial release still fails
closed. Fifty-seven focused analytics, worker, renderer, portfolio API, and
release-audit tests pass, and full-repository static type checking reports no
issues.

## Production acceptance requirements

This phase is not production-complete until all of the following are true:

1. The complete release gate and service-container builds pass.
2. The change is deployed to API, worker, scheduler, and web services as
   applicable.
3. All Egg cases have a final administrator outcome, including any explicit
   insufficient-evidence exclusions.
4. A new immutable governed Egg replay completes with automatic fallback off.
5. All certified comparable relationships reconcile overall and by retailer,
   including Sam's Club, ShopRite, and Trader Joe's.
6. The six portfolio materializations pass the semantic release audit.
7. Every primary report tab, retailer filter, comparison basis, radius, drawer,
   map, and export is exercised in production with no trust-critical discrepancy
   or browser error.
8. The owner/admin documentation is updated from pending to deployed with the
   exact CI run, replay ID, materialization counts, and live acceptance results.
