# Phase 13.26 — Egg Reporting Acceptance and Trust Audit

## Status

Production complete and owner-ready on August 20, 2026. The platform owner
completed all 185 review cases, the generation-two governed replay retained all
183 certified-comparable relationships, all six comparison-basis/radius
documents passed the semantic release audit, and the primary production report
workflow passed live browser acceptance. Four superseded Egg reports were then
recoverably archived. Source Search data, PDP evidence, certification history,
immutable releases, and audit lineage remain preserved.

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

Generation two produced immutable analysis
`fresh_shell_eggs-0474c5c1-3949-4623-ac12-7aa76f838bcc-match-v2-3c967ecc-r2`
with ready-to-share validation, all 183 certified-comparable relationships,
three Price Architecture matrices, and no fallback. Its first competitive
portfolio build exposed a scalability defect before promotion: each of 108
compatible benchmark-product groups independently reloaded and rerendered the
same multi-megabyte immutable analysis and publication. The all-retailer build
crossed the 15-minute caller boundary without storing a partial portfolio.

Competitive Product Leadership now has a bounded, concurrency-safe immutable
analysis/report context cache. Concurrent product groups share one database
load and one governed report rendering per analysis instead of repeating that
work hundreds of times. The cache is safe because both AnalysisResult and its
publication are immutable; it does not cache mutable collection or review
state. Focused tests verify concurrent request coalescing as well as all
existing portfolio formula and semantic-audit behavior. The generation-two
AnalysisResult remains valid and will be rematerialized after this API-only
performance correction; no new matching replay or paid call is required.

The optimized rematerialization built all six documents in 181.9 seconds, but
the final semantic audit correctly rejected them. Kroger had one certified
relationship and Sam's Club had its single certified relationship without a
positive benchmark Search observation available to the product-location
projector. The scorecard declared those governed identities while its evidence
drawer omitted them, causing benchmark-product, competitor-product, and
relationship-count mismatches at all three compatible radii.

Portfolio projection now retains such certified identities as explicit
zero-scored product and relationship rows. This does not invent availability,
price, or location coverage: all product-location measures remain zero and the
scorecard surfaces the existing no-scored-evidence limitation. It does ensure
that declared certification counts, included-product drawers, and audit rows
share one complete identity ledger. Regression coverage includes a certified
relationship whose benchmark product has no positive Search observation and
requires identity continuity with zero scored evidence.

## Production acceptance record

The accepted generation-two replay is:

- analysis run: `05aa5182-e636-495c-bafb-c8040f44bd34`;
- analysis: `fresh_shell_eggs-0474c5c1-3949-4623-ac12-7aa76f838bcc-match-v2-3c967ecc-r2`;
- AnalysisResult database ID: `bfaf8389-6f5c-4748-b1a8-a0e445ccbe20`;
- AnalysisResult checksum:
  `1515aa5d16e3be114e16e66cc99611cf9d8810347e14e823d57e5bb892200e43`;
- immutable gold-set release: `3c967ecc-17fd-4bad-a749-c223519723d0`; its
  complete checksum remains preserved in the immutable release and audit
  records.

The final rebuild generated all six global portfolio documents—Compatible-spec
and Strict exact-spec at 1, 3, and 5 miles—in 156.288 seconds without a
MetricsCart or OpenAI call. The semantic portfolio audit passed with zero
errors. Its 51 warnings are explicit evidence limitations, not reconciliation
defects: a retailer/basis can have a certified identity relationship but no
positive-price product-location evidence that is scorable under the selected
geography policy.

Compatible-spec retains 183 declared relationships and 183 relationship
evidence rows at every radius. Strict exact-spec retains seven and seven.
Compatible-spec includes all 13 configured competitors; seven have locally
scored evidence in this snapshot and six retain their certified product and
relationship identities with zero-scored evidence rather than disappearing or
being represented as a price result. At three miles, scored observations include
Target 5,096, Amazon Same Day 3,255, ALDI 2,826, Albertsons 892, Safeway 844,
HEB 663, and Kroger 21. Giant Eagle, Meijer, Sam's Club, ShopRite, Trader Joe's,
and Wegmans have no scorable local price evidence in the accepted snapshot.

Production API acceptance returned HTTP 200 for all six profile/radius
documents in 24–138 milliseconds. Live browser acceptance exercised all nine
report tabs, retailer and basis filters, 1/3/5-mile controls, included-product
drawers, evidence rows, maps, and export controls with a clean browser console.
The report opens on Compatible-spec by default because that is the broadest
certified comparison basis; Strict exact-spec remains an explicit selection.
The Retailer Scorecards landing page uses the radius-native document for its
summary and no longer mixes in the legacy exact-ZIP executive narrative.

Commit `1b96298` preserves unscored certified identities without inventing
price or location evidence. GitHub Actions run `32433669906` passed the complete
release gate. Commit `0939890` aligned the landing context, default basis, and
executive summary to the radius-native evidence; GitHub Actions run
`32434666036` passed the complete release gate, including contracts, reversible
migrations, Python and web tests, 13 browser tests, the production Next.js
build, and all four service-container builds. Railway web was verified at the
exact `0939890` revision before final browser acceptance.

After the replacement passed these checks, the following exact obsolete
AnalysisResults were recoverably archived at
`2026-08-21 01:04:53.859010+00:00`:

- `fresh_shell_eggs-0474c5c1-3949-4623-ac12-7aa76f838bcc-match-v2-de5fc82e`;
- `fresh_shell_eggs-0474c5c1-3949-4623-ac12-7aa76f838bcc-match-v2-de5fc82e-r2`;
- `fresh_shell_eggs-0474c5c1-3949-4623-ac12-7aa76f838bcc-match-v2-80afd160`;
- `fresh_shell_eggs-0474c5c1-3949-4623-ac12-7aa76f838bcc-match-v2-3c967ecc`.

Only `analysis_result.archived_at` changed for those resolved IDs. No row was
deleted, the accepted `-r2` replacement remains active, and source data, raw
objects, PDP evidence, review decisions, queue history, immutable releases,
materialized reporting evidence, and audit lineage were not modified.

## Acceptance requirements

All requirements below are satisfied:

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
