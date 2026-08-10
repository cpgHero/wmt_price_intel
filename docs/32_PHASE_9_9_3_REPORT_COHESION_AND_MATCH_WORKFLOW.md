# Phase 9.9.3 — Report Cohesion, Comparison-Basis Integrity, and Insight-to-Match Workflow

## Status

Implemented and regression-certified on 2026-08-10 after explicit approval. Railway promotion is
tracked as the final deployment gate for renderer version 2.14.0.

## Outcome

Make the application, shareable HTML, leadership email, and workbook tell one coherent story from
the same deterministic report projection:

1. What is the competitive position for the selected retailer and comparison basis?
2. Which product relationships support that position?
3. Which products need attention, which positions should be protected, and where?
4. Is the supporting relationship confirmed, suggested, ambiguous, rejected, or insufficient?
5. Can the reader inspect the evidence, correct a relationship, and deliberately re-evaluate the
   analysis without triggering provider calls?

The phase closes semantic and workflow gaps before Phase 10. It does not add new retailers,
collection geography construction, or category-specific core logic.

## Why this phase is required

The cross-report audit found that the current surfaces are technically stable but not yet
semantically unified:

- Comparison records retain a comparison profile/lens internally, but the Segments views omit it.
  Identically named segments can therefore appear more than once with different outcomes and no
  visible explanation.
- A comparison lens and a product segment are different concepts. The current UI makes them appear
  interchangeable.
- Confirmed human relationships are globally one-to-one, while ungoverned automatic candidates
  can still create many-to-one relationship output across lenses.
- The current segment leader presentation drops parity. This can declare a price leader when the
  dominant result is actually parity.
- Retailer scorecards can use a deterministic fallback lens, but the report header describes every
  row as if it used the strict exact-package lens.
- Product decisions can admit suspicious package comparisons and extreme gaps even when Product
  Pack QA rules already indicate that unit or package semantics need review.
- Product cards, maps, assortment findings, and narrative references do not share one pair-detail
  workflow. Match actions exist only in the Match Review surface.
- The application, HTML, email, and workbook are based on the same analysis but do not yet expose
  the same navigation, relationship status, comparison basis, readiness, and revision context.

Passing unit tests alone cannot catch these meaning and decision-flow defects. Phase 9.9.3 adds the
normative contracts and regression tests that can.

## Definitions and analytical grains

| Term | Meaning | Grain | May drive price outcomes? |
| --- | --- | --- | --- |
| Reference retailer | The named retailer whose position is being evaluated, initially Walmart (US) | Retailer | Yes |
| Competitor | One selected retailer compared with the reference retailer | Retailer | Yes |
| Comparison profile / lens | Product Pack rule defining geography, attributes, price metric, availability, and package basis | Profile | Yes |
| Segment | A category-specific attribute grouping produced by Product Pack configuration | Segment | Yes, only inside a named lens |
| Candidate edge | A deterministic Product Pack-eligible product pairing that has not passed relationship governance | Product pair | No executive product claim |
| Product relationship | One reference product paired to one competitor product, with one or more eligible lenses | Stable product pair | Yes when decision-ready |
| Store evidence | Search-backed prices for one relationship, lens, and retained geography | Pair × profile × geography | Yes |
| PDP enrichment | Non-price identity, attribute, description, URL, and image evidence | Product × observed price state | No price calculation |
| Parity | Absolute price difference is within the Product Pack tolerance | Retained comparison | Yes, as a first-class outcome |
| Whitespace | An in-scope product with no decision-ready counterpart after unresolved candidates are separated | Retailer product | No direct price claim |

“Relationship,” “comparison,” “match,” and “segment” will not be used as interchangeable labels.
Every quantitative price surface must identify its comparison profile and price metric.

## Non-negotiable integrity rules

1. Search observations remain authoritative for store-specific price, availability, store, ZIP,
   and observed geography.
2. PDP enrichment may improve identity and attribute confidence, but it may not replace Search
   price or create a price observation.
3. The deterministic engine calculates all counts, shares, gaps, medians, ranks, parity, and
   geographic outcomes. The LLM may explain only persisted claims that pass the claim critic.
4. One active relationship is one reference product to one competitor product per organization,
   Product Pack version, and competitor. The relationship may be eligible for multiple lenses.
5. A product cannot participate in two active relationships for the same competitor merely because
   the display lens changes.
6. Ambiguous automatic candidate groups are review work, not active relationships. They do not
   feed executive product decisions or relationship-based assortment coverage.
7. Segment price outcomes use decision-ready one-to-one relationships. Broader candidate coverage
   may be reported separately as eligibility, never as a relationship or price win.
8. Benchmark-lower, competitor-lower, and parity counts use one denominator and reconcile to the
   retained comparison count. Their displayed shares must sum to 100% within rounding tolerance.
9. A package-price decision is suppressed when unit/package semantics are unresolved or violate a
   Product Pack QA rule. A normalized-unit lens may remain eligible when its own inputs are valid.
10. Every publication and derivative surface shows the analysis result, renderer version, match
    revision, selected comparison basis, and readiness status applicable to the claims being shown.
11. Saving a match decision stages an immutable revision. It never triggers reanalysis, Search,
    PDP, or OpenAI. Re-evaluation remains a separate explicit action with a separate choice for
    applying the revision to future collections.
12. No category-specific branch is added to the core engine. New category nuance remains Product
    Pack configuration plus generic matching, QA, and presentation capabilities.

## 9.9.3.1 — Normative presentation and vocabulary contracts

### Shared `ReportView` contract

Add `schemas/report-view.schema.json` as the normative delivery contract produced by Python and
consumed by TypeScript and every renderer. `AnalysisResult` remains the immutable analytical source;
`ReportView` is a deterministic projection, not a second source of truth.

The contract will include:

- `analysis_id`, source checksum, publication ID, AnalysisResult schema version, renderer version,
  and generated timestamp;
- named `retailer_scope`, selected/all-competitor scope, and catalog-resolved display names;
- `comparison_bases`, each with profile ID, display label, geography method, comparison metric,
  price unit, package basis, and availability policy;
- `segment_comparisons`, each carrying an explicit basis/profile and all three price outcomes;
- `product_relationships`, each carrying a stable deterministic relationship ID, product IDs,
  state, origin, eligible profile IDs, evidence counts, QA state, and PDP/search source roles;
- `retailer_scorecards`, including the actual basis used by each row and any fallback status;
- `match_governance`, including mode, consumed revision, proposed/confirmed/rejected/ambiguous
  counts, and staged-revision status;
- `report_readiness`, including `ready`, `review_required`, or `limited`, blocking reasons,
  warnings, and suppressed-decision counts;
- the report groups/sections used by web, HTML, email, and workbook; and
- evidence references sufficient to reproduce every displayed deterministic claim.

Python models validate the projection before persistence or rendering. TypeScript types are
generated from the same schema. Legacy publications receive an explicit compatibility projection;
missing basis or governance fields are displayed as unavailable, not inferred by the browser.

### Product Match Review contract

Extend `schemas/product-match-review.schema.json` with:

- `ambiguous` candidate-group state separate from `suggested` relationships;
- stable `candidate_group_id` and `relationship_id` values;
- `eligible_profile_ids` and per-profile evidence on every candidate;
- `qa_status`, machine-readable `suppression_reasons`, and missing-attribute evidence;
- `other_lens_participation` for unmatched/manual-builder products; and
- staged revision, applied-policy revision, and current publication revision metadata.

The existing persisted human states remain `confirmed` and `rejected`. Ambiguity is derived from
the current immutable input and Product Pack; it is not stored as a human decision.

### Product Pack extensions

Extend the generic Product Pack schema with `reporting.decision_rules`:

- profile priority and scorecard eligibility;
- minimum retained observations and geographies for an executive product decision;
- allowed relationship states for summary, product, and segment price surfaces;
- package/unit confirmation requirements;
- extreme-gap review behavior;
- parity display policy; and
- optional preferred scorecard profile.

All five current Product Packs will declare these values. The engine evaluates the configuration;
it will not inspect a category ID.

### Vocabulary normalization

User-facing copy will use:

- “Walmart (US)” or the catalog-resolved retailer name, never “Benchmark” as a retailer label;
- “comparison lens” in navigation and controls;
- “segment” only for Product Pack attribute groupings;
- “relationship” for a stable one-to-one product pair;
- “suggested relationship” only after a candidate is uniquely resolvable;
- “ambiguous candidates” when review is required;
- “typical price difference” with an explicit direction, for example “ALDI was typically $0.22
  lower,” rather than an unexplained signed gap; and
- “Key points” instead of vague or overly prescriptive “What to do” sections.

## 9.9.3.2 — Deterministic one-to-one automatic relationship resolution

Automatic candidates will be resolved before any pair-level metric or card is projected:

1. Normalize stable string product IDs and consolidate duplicate listings.
2. Build eligible candidate edges from Product Pack matching profiles and retained Search inputs.
3. Merge the same product pair across lenses into one candidate with multiple eligible profiles.
4. Remove rejected pairs and apply confirmed human relationships first.
5. Remove every automatic edge that conflicts with a confirmed relationship.
6. Partition remaining edges into bipartite conflict components per competitor and Product Pack
   version.
7. Rank only by generic semantic evidence: configured profile priority, exactness of matching
   attributes/package basis, attribute completeness/confidence, and QA eligibility. Evidence volume
   is displayed but does not decide product identity. Stable IDs provide output ordering only.
8. Admit automatic relationships only when the best maximum one-to-one assignment is unique on
   semantic evidence. If more than one equally valid assignment remains, emit an ambiguous
   candidate group instead of choosing through a hidden ID tie-break.
9. Project new unmatched products and ambiguous groups into Match Review. Exclude ambiguous edges
   from executive product decisions, relationship coverage, and price outcome denominators.

This preserves one-to-one integrity without requiring every unique Product Pack suggestion to be
manually confirmed. Suggested relationships remain visibly distinct from confirmed relationships.
A report with material ambiguous groups is `review_required`, not silently “ready to share.”

### Relationship and segment calculations

- Pair-level product decisions use only confirmed or uniquely suggested relationships that pass the
  selected lens's Product Pack decision rules.
- Segment-level price outcomes aggregate retained store evidence from those same decision-ready
  relationships within a named lens.
- Candidate eligibility and assortment breadth may count broader eligible products in separately
  labeled fields. They may not be called matches, relationships, wins, or losses.
- One relationship can contribute to multiple lenses only when `eligible_profile_ids` and the
  relevant price inputs support each lens.
- If a lens has no decision-ready relationships, the UI reports that state and links to filtered
  Match Review rather than reusing another lens or rendering an empty leader card.

## 9.9.3.3 — Comparison-basis, parity, evidence, and readiness integrity

### Outcome model

Every comparison surface uses the same three-outcome model:

```text
retained comparisons = reference lower + competitor lower + parity
```

The dominant result may be parity. No retailer is called the leader when both lower-price shares are
zero or parity is the largest outcome. “Lower-price share” becomes “Price outcome mix,” with all
three outcomes visible and product thumbnails only when a row represents a decision-ready product
relationship.

### Scorecard basis

- Each retailer scorecard row displays the exact comparison lens it uses.
- The all-retailer view uses one configured scorecard lens where available.
- A deterministic fallback is allowed only when labeled on that retailer's row.
- Rows using different lenses are not assigned a cross-retailer rank and are not described as
  directly comparable.
- A selected-retailer view receives its own deterministic summary rather than an empty portfolio
  narrative placeholder.

### Product-decision guardrails

Before a product decision can appear on Overview, Products, Geography, or in leadership prose:

- the relationship must be confirmed or uniquely suggested;
- the selected lens must be eligible for that relationship;
- the Search-backed observation and geography minimums must pass;
- required package/unit attributes must be resolved;
- Product Pack QA and extreme-gap checks must pass; and
- a deterministic plain-language statement must reconcile to the displayed evidence.

Suppressed decisions remain visible in Quality and Match Review with an exact reason. Examples such
as a single unit compared with a 12-unit multipack must not appear as a package-price opportunity
unless a Product Pack explicitly defines equivalence.

### Readiness model

`report_readiness` is deterministic:

- `ready`: all executive product claims pass, shares reconcile, no material ambiguity remains, and
  the current publication records its relationship revision;
- `review_required`: ambiguous candidates, incompatible package semantics, unresolved high-impact
  gaps, or a staged-but-not-re-evaluated relationship revision could materially change the report;
  and
- `limited`: the analysis is valid but evidence is too sparse for the requested decision surface.

Readiness is not an AI score. Blocking reasons link directly to the affected lens, relationship,
Quality evidence, or Match Review queue.

## 9.9.3.4 — Cohesive report information architecture

The application and shareable HTML will use the same ordered report groups:

1. **Overview** — retailer scorecards, selected-lens outcome mix, top validated product positions,
   concise Key Points, readiness, and revision context.
2. **Price & Segments** — comparison-lens selector, explicitly labeled segment outcome matrix,
   parity, typical price difference in plain language, and evidence volume.
3. **Products** — decision-ready one-to-one relationships ranked by deterministic magnitude,
   breadth, and evidence; positions needing attention and positions to protect.
4. **Geography** — a product/lens-filterable map plus a compact regional summary. The initial
   distance controls become 1, 3, and 5 miles when proximity profiles are implemented; no unlabeled
   10-mile card is retained as a general KPI.
5. **Assortment** — distinct products, decision-ready relationship coverage, ambiguous candidates,
   retailer-only products, competitor whitespace, and store/ZIP breadth from the reference
   retailer's perspective.
6. **Match Review** — relationship queue, ambiguous groups, manual builder, staged revision, and
   deliberate re-evaluation controls.
7. **Quality & Methodology** — excluded/suppressed examples, sample-versus-total disclosure,
   package and unit issues, source authority, methodology, and evidence lineage.
8. **Exports** — current HTML, workbook, leadership email/attachment, revision status, publication
   version, and regeneration controls.

The current prose-only Opportunities content moves into validated Key Points on Overview and
Products. Duplicate outcome graphics are removed from tabs where they do not answer the next user
question.

### URL and state contract

Report state is deep-linkable and reload-safe:

```text
?competitor=<retailer-id>&tab=<group-id>&lens=<profile-id>&pair=<relationship-id>
```

Invalid or legacy values fall back safely and are removed from the canonical URL. Selecting a
retailer, tab, lens, or pair updates the URL without losing the other selections. HTML fragment and
query navigation follows the same identifiers.

## 9.9.3.5 — Universal Pair Detail and insight-to-match workflow

One reusable Pair Detail drawer will open from product cards, outcome rows, map findings,
assortment findings, quality issues, and pair references in Key Points.

It contains:

- both retailer names, product images, names, URLs, and stable IDs;
- current state and origin: suggested, confirmed, rejected, ambiguous, or unavailable;
- eligible lenses and the currently selected comparison basis;
- side-by-side PDP identity/specification evidence, with explicit missing-data states;
- deterministic attribute and package compatibility rationale;
- Search-backed price outcome summary and observation/market counts;
- paginated or virtualized store evidence with a complete CSV/XLSX download;
- Confirm, Reject, Undo/return to Product Pack suggestion, or Replace actions when allowed;
- an explanation that changes are staged and have not updated the report; and
- links to the relationship's filtered location in Match Review and Quality.

The drawer never recalculates analytics. It renders the shared projection and calls the existing
revision APIs for mutations.

### Match Review behavior

- Confirm/reject/undo actions are available in both Pair Detail and Match Review, with identical
  replacement and stale-revision safeguards.
- A rejected or unmatched product returns to the manual builder unless another active relationship
  uses it.
- Manual-builder products indicate active or suggested participation in every other eligible lens.
- Confirmed products remain locked globally for the selected competitor unless the user explicitly
  replaces the relationship.
- “Reset” is renamed “Undo decision” or “Return to Product Pack suggestion,” depending on the prior
  state.
- A staged-change banner appears on every report group and export surface until the user explicitly
  re-evaluates.
- Re-evaluate offers exactly two choices: this report only, or this report and future collections.
  Both reuse immutable inputs and consume no provider or OpenAI credits.

## 9.9.3.6 — Surface parity and report-index cohesion

### Application and shareable HTML

The web application and standalone HTML use the same group order, headings, comparison basis,
retailer filter, product relationship states, readiness status, pair-detail content, map model, and
revision context. Static HTML may replace mutation controls with a deep link back to the application,
but it must not display an older analytical structure.

### Leadership email

The email remains concise and includes:

- portfolio or selected-retailer scorecard using the actual named lens;
- the most material validated product positions;
- parity and evidence caveats where material;
- readiness and match-revision context; and
- the current HTML report as the single “Report” attachment/link.

It does not include ambiguous or suppressed product decisions as recommendations.

### Workbook

The workbook includes numeric, filterable sheets for retailer scorecards, segment outcomes,
product relationships, store evidence, assortment, suppressed decisions, and methodology. Each
row carries retailer, comparison profile, relationship state, revision, and evidence references.

### Analyses index

Each publication row displays product/category, named reference retailer, competitor count,
publication date/version, report readiness, match revision, staged-change warning, and material
quality flags. Obsolete historical publications remain immutable but can stay archived from the
default view.

## 9.9.3.7 — Accessibility, performance, and visual behavior

- Report tabs implement the keyboard tab pattern and preserve URL state.
- Drawers trap focus, close with Escape, label controls, and restore focus to the opener.
- Map points are keyboard operable and have non-color outcome labels.
- Outcome colors and retailer identity are accompanied by text and/or logos.
- Evidence tables are paginated or virtualized; the browser does not render thousands of store rows
  at once.
- Quality samples state both displayed and total counts, for example “160 of 340 issues.”
- Raw methodology JSON moves behind a developer/audit disclosure; the default methodology is
  readable business language with exact source lineage.
- Missing PDP images/details use explicit Search fallback or a neutral missing state. They do not
  block a valid price comparison unless an identity/attribute rule requires the missing field.

## Implementation sequence and approval gates

### Gate A — Contracts and fixtures

1. Add the ReportView, Match Review, and Product Pack schema changes.
2. Generate Python/TypeScript models and update canonical examples.
3. Update all five Product Packs without category branches.
4. Add fixtures for parity dominance, fallback scorecards, ambiguous candidate graphs, multipack
   suppression, sparse evidence, and staged revisions.

Exit: contracts validate in both runtimes, and current publications load through the documented
legacy compatibility projection.

### Gate B — Deterministic analytics and projection

1. Add generic one-to-one automatic relationship resolution and ambiguity detection.
2. Separate eligibility coverage, active relationships, and segment aggregations.
3. Add three-outcome parity reconciliation and Product Pack decision guardrails.
4. Project readiness, suppression reasons, scorecard basis, and selected-retailer summaries.

Exit: five category goldens pass with no many-to-one active relationship, no unlabeled lens, and no
unreconciled outcome shares.

### Gate C — Shared workflow and report UI

1. Reorganize the report groups and add URL state.
2. Build the universal Pair Detail drawer and connect every pair-bearing insight.
3. Align Match Review, Assortment, Products, Geography, and Quality around the same relationship
   IDs and states.
4. Add staged-change/readiness banners and accessible behavior.

Exit: a user can travel from an executive finding to its relationship and store evidence, stage a
decision, return to the report without recalculation, and deliberately re-evaluate.

### Gate D — Artifact parity and publication rollout

1. Update HTML, email, workbook, and Analyses index from the shared ReportView contract.
2. Increment the renderer version; do not mutate prior artifacts.
3. Replay the five historical categories with existing inputs and cached PDP evidence.
4. Compare application, HTML, email, and workbook values and labels programmatically and visually.
5. Deploy backward-compatible API/worker changes before the web and renderer release.

Exit: category certification and Railway smoke tests pass. No live MetricsCart, new PDP, or OpenAI
call is required for this phase's regression replay.

## Expected code and contract touch points

The exact file list will be confirmed at Gate A, but the intended boundaries are:

- `schemas/report-view.schema.json`
- `schemas/product-match-review.schema.json`
- `schemas/product-pack.schema.json`
- `product-packs/*.json`
- `packages/python/rci-analytics/src/rci_analytics/matching.py`
- `packages/python/rci-analytics/src/rci_analytics/presentation.py`
- `packages/python/rci-analytics/src/rci_analytics/assortment.py`
- `packages/python/rci-results/src/rci_results/blueprints.py`
- `packages/python/rci-results/src/rci_results/match_review.py`
- `packages/python/rci-results/src/rci_results/renderers.py`
- `apps/web/src/app/analyses/[analysisId]/workspace.tsx`
- `apps/web/src/app/analyses/[analysisId]/match-review-workbench.tsx`
- new reusable report route-state and Pair Detail components under the analysis route; and
- Python, TypeScript, renderer, API, integration, and browser regression tests.

### Database decision

No new migration is planned. Human revision and future-collection application policy already have
durable storage. Automatic ambiguity, readiness, and presentation state are deterministic products
of an immutable analysis input and belong in the ReportView/publication projection. If Gate A finds
a requirement for independently queryable durable state, a migration must be proposed separately
before it is written.

## KPI and guardrail definitions

### Primary decision metrics

1. **Decision-ready relationship coverage** — distinct in-scope products participating in a
   confirmed or uniquely suggested, QA-eligible relationship divided by distinct eligible products,
   reported separately for each retailer and competitor.
2. **Price outcome mix** — reference-lower, competitor-lower, and parity shares for one selected
   retailer and lens using the same retained-comparison denominator.
3. **Evidence-ready product positions** — active relationships meeting configured observation,
   geography, package, and QA requirements for an executive product claim.

### Diagnostic drivers

- ambiguous candidate groups;
- unmatched and retailer-only products;
- suppressed product decisions by reason;
- products eligible only for normalized-unit lenses;
- PDP identity/image completeness, explicitly separate from Search price completeness; and
- store/ZIP breadth behind each product position.

### Release guardrails

- zero product IDs used in more than one active relationship for the same competitor scope;
- zero segment/outcome rows without a visible profile and price metric;
- zero executive product cards with unresolved package/unit semantics;
- outcome counts reconcile and shares sum to 100% within rounding tolerance;
- all user-facing retailer names resolve through the retailer catalog;
- current and staged match revisions are visible on every delivery surface; and
- app, HTML, email, and workbook agree on basis, value, relationship state, and readiness.

## Acceptance tests

### Contract and integrity

1. Python and TypeScript validate the same ReportView fixture.
2. Every segment row includes profile ID, label, metric, geography, and relationship grain.
3. Duplicate candidate edges across lenses collapse to one relationship with multiple eligible
   profiles.
4. No product participates in two active automatic or confirmed relationships for one competitor.
5. A conflict graph with two equally valid assignments becomes ambiguous and is excluded from
   pair-level decisions.
6. A uniquely resolvable automatic graph produces stable relationship IDs independent of input row
   order.
7. Confirmed decisions displace conflicts; rejected pairs do not reappear; newly observed products
   remain eligible for review.
8. A single-unit/multipack package comparison is suppressed while a valid normalized-unit lens can
   remain available.
9. PDP fields never change persisted Search price, store, ZIP, or availability.

### Metrics and readiness

10. Reference-lower, competitor-lower, and parity counts reconcile exactly.
11. A parity-dominant banana fixture displays parity as the dominant outcome and no false retailer
    leader.
12. A fallback egg scorecard identifies its compatible-spec lens and is not ranked as directly
    comparable with strict-lens rows.
13. A staged relationship revision sets `review_required` and does not alter the current published
    values.
14. Sparse or suppressed evidence cannot produce an executive product decision.
15. Assortment separates decision-ready relationships, candidate eligibility, ambiguous groups,
    and whitespace without double-counting products across lenses.

### Workflow and surface parity

16. A product reference from Overview, Products, Geography, Assortment, or Quality opens the same
    Pair Detail content.
17. Pair Detail actions stage a revision but enqueue no analysis or provider task.
18. Explicit re-evaluation creates a new immutable AnalysisResult and preserves the prior
    publication.
19. Competitor, tab, lens, and pair URL state survives reload and supports a direct link into
    filtered Match Review.
20. Focused-retailer views contain no other competitor's rows or portfolio-only prose.
21. Application, HTML, email, and workbook fixtures agree on scorecard basis, product outcome,
    readiness, and match revision.
22. Evidence drawers are keyboard accessible and do not render an unbounded store table.
23. Ground beef, eggs, milk, bananas, and strawberries pass their category goldens without a
    category-specific branch in core analytics or presentation code.

## Exact verification commands

```bash
pnpm --filter @rci/contracts check
.venv/bin/ruff check packages/python/rci-analytics packages/python/rci-results apps/api apps/worker
.venv/bin/pytest \
  packages/python/rci-analytics/tests/test_matching.py \
  packages/python/rci-analytics/tests/test_presentation.py \
  packages/python/rci-analytics/tests/test_assortment.py \
  packages/python/rci-results/tests/test_blueprints.py \
  packages/python/rci-results/tests/test_match_review.py \
  packages/python/rci-results/tests/test_results.py \
  apps/api/tests/test_analyses.py -q
pnpm --filter @rci/web typecheck
pnpm --filter @rci/web test
pnpm --filter @rci/web build
.venv/bin/python scripts/validate_handoff.py
.venv/bin/pytest \
  packages/python/rci-analytics/tests/test_full_ground_beef_golden.py \
  packages/python/rci-analytics/tests/test_full_egg_golden.py \
  packages/python/rci-analytics/tests/test_full_milk_golden.py \
  packages/python/rci-analytics/tests/test_full_banana_golden.py \
  packages/python/rci-analytics/tests/test_full_strawberry_golden.py -q
```

Browser certification will additionally cover the five historical publications at desktop and
mobile widths, keyboard navigation, report-to-Match-Review deep links, staged decisions, and
app-versus-HTML visual/content parity.

## Railway deployment sequence

1. Take a production database backup and record current web, API, worker, and renderer versions.
2. Deploy backward-compatible contract/projection changes to API and worker.
3. Run schema and historical-publication compatibility smoke tests; no migration is expected.
4. Deploy the web application with support for both legacy and Phase 9.9.3 ReportView projections.
5. Deploy the incremented renderer and generate new immutable publications for the five historical
   certification cases using existing inputs and cached enrichment.
6. Verify application, HTML, email, and workbook parity plus zero provider calls during relationship
   revision/re-evaluation tests.
7. Promote the new publications after readiness and visual certification. Retain prior artifacts
   immutably and archived from the default list where appropriate.

Rollback is service-version rollback plus continued use of the prior immutable publication; no
destructive data rollback is planned.

## Explicitly deferred

- Phase 10 collection-definition and dynamic geography construction;
- 1/3/5-mile proximity profiles beyond replacing misleading general-purpose 10-mile presentation;
- onboarding additional retailer adapters;
- new live Search/PDP collection or paid AI experimentation;
- automatic retailer price changes or prescriptive execution recommendations; and
- category-specific core code.

## Blocking questions

None. Current contracts, historical inputs, cached enrichment, five category benchmarks, retailer
catalog, and prior phase decisions are sufficient to implement this plan after approval.
