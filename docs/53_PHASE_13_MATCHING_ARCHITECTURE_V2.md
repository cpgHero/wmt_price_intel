# Phase 13 — Matching Architecture v2

## Outcome

Phase 13 introduces a category-neutral, evidence-governed product matching foundation without
changing the current authoritative matcher or historical publications until the replacement path
passes shadow-mode certification. The atomic source of truth becomes a versioned pairwise match
edge. Business-facing one-to-one, many-to-one, one-to-many, cohort, assortment, and store-level
views are derived from those edges without losing their underlying evidence.

The phase combines the existing application's strongest controls—immutable Product Packs, Search
price authority, PDP identity enrichment, Retailer Packs, match and brand revisions, explicit
reanalysis, and store-level Product Leadership—with a richer identity, attribute-evidence, tier,
catchment, and comparison-observation model.

## Non-negotiable analytical invariants

1. Search is authoritative for location-specific price and observed availability. A positive
   Search price means observed available in that collection; it is not a promise of live inventory.
2. The location master is authoritative for store identity and coordinates. ZIP is a fallback and
   reporting dimension when physical coordinates are available.
3. PDP, manufacturer, brand-foundation, OCR, and vision evidence may support identity and product
   attributes. None may replace Search price.
4. Retailer listing identity, exact trade-item identity, product equivalence, comparison
   eligibility, and local applicability are separate governed claims.
5. Unknown values remain unknown. Unknown-versus-unknown never counts as agreement.
6. Price similarity is never a semantic matching signal.
7. LLMs, embeddings, OCR, and image models may extract evidence, expand candidate recall, and
   prioritize review. They never compute authoritative metrics or silently approve a relationship.
8. Every published aggregate reconciles to immutable local comparison observations and exposes its
   numerator, denominator, price basis, policy version, match tier, geography, and coverage state.
9. Manual changes create a new immutable revision, do not immediately reanalyze, and apply to
   future collections only after an explicit user choice.
10. Category behavior remains in Product Packs. Retailer behavior remains in Retailer Packs. The
    core engine contains no milk-, egg-, beef-, strawberry-, or banana-specific branches.

## Vocabulary and decision grain

### Identity

- **Retailer listing** — one retailer product ID, PDP/search representation, seller, URL, and
  fulfillment context.
- **Trade item** — one verified physical package configuration, normally supported by a GTIN/UPC
  or manufacturer identifier plus non-contradictory package evidence.
- **Attribute fact** — one raw and normalized attribute value with source, observation time,
  extraction method, reliability, review status, and Product Pack version.

The existing `canonical_product` record remains backward compatible but is treated as a retailer
listing identity. Phase 13 does not destructively repurpose or merge existing records.

### Match tiers

1. `exact_item` — the same verified physical trade item and package.
2. `exact_specification` — different identities or brands, but all required Product Pack attributes
   and package quantity agree.
3. `equivalent_product` — the same consumer need and quality proposition with only explicitly
   permitted differences.
4. `comparable_substitute` — a relevant shopper alternative with material differences that remain
   visible.
5. `custom_approved` — a human-approved relationship for a named business purpose, scope, and
   effective period.

`unresolved` and `not_comparable` are statuses, not tiers. Brand relationship, price basis, and
geographic applicability are independent dimensions.

### Cardinality

Semantic edges are pairwise and may overlap. A competitor product may participate in several
approved edges when the evidence supports each claim. Cardinality is controlled at the result
grain rather than by suppressing defensible semantic edges.

The authoritative product-level grain is:

```text
match policy revision
× benchmark listing
× benchmark location
× competitor retailer
× comparison basis
× observation period
```

All eligible competitor offers may be retained, but the published controlling offer is selected
by an explicit policy such as lowest eligible local offer, nearest eligible offer, or representative
assortment. Executive store scorecards count a benchmark store once while separately exposing
product-location outcomes. A simple average of several products is never silently compared with
one competitor product.

## Processing order

1. Persist immutable raw Search and PDP evidence.
2. Normalize retailer, location, identifier, timestamp, fulfillment, and price fields.
3. Deduplicate Search placements at product × location × collection grain while retaining
   sponsorship evidence.
4. Apply Product Pack qualification with `include`, `exclude`, or `review` and a reason code.
5. Resolve retailer listing identity and exact trade-item links.
6. Enrich each distinct in-scope listing once per freshness policy, with targeted location samples
   only for contradictory identity evidence or governed price-regime diagnostics.
7. Materialize attribute facts and conflicts with complete provenance.
8. Generate high-recall candidates using category blocks and no known hard conflicts.
9. Apply deterministic tier rules and compute evidence coverage independently from similarity.
10. Approve, review, reject, or defer each pairwise edge.
11. Resolve local applicability using the configured store catchment and observation window.
12. Materialize all eligible local comparisons and the policy-selected controlling comparison.
13. Reconcile atomic observations to item, store, cohort, brand, assortment, and retailer rollups.
14. Publish only after contract, quality, and trust gates pass.
15. Monitor identifier, title, package, attribute, brand, image, supplier, distribution, and policy
    drift and queue affected edges for revalidation.

## Coverage taxonomy

Semantic, availability, and price coverage are reported separately. Every unscored local context
has one primary reason:

- `no_eligible_match`
- `no_geographic_overlap`
- `matched_product_not_observed`
- `price_unavailable_or_stale`
- `collection_failure`
- `attribute_evidence_incomplete`
- `match_review_required`

No missing comparison is represented by an unexplained null.

## Product Pack contract

Product Packs remain executable category contracts and will progressively declare:

- critical attributes and their identity/match roles;
- hard blockers and required exact attributes;
- normalization and allowed-tolerance rules;
- tier admission rules;
- missing-value policy;
- evidence precedence;
- brand/value-position policy;
- valid price bases;
- candidate blocks;
- geography applicability rules;
- rollup policies; and
- effective dates and certification state.

Existing matching profiles remain supported. Phase 13 adds a v2 policy compiler rather than
breaking older Product Pack versions.

## Retailer Pack contract

Retailer Packs own retailer-specific ID and URL rules, store/service-area behavior, location-master
mapping, Search/PDP field precedence, private-label ownership and aliases, seller/marketplace
eligibility, fulfillment defaults, sponsorship mapping, PDP freshness, known placement-duplicate
behavior, catchment options, and provider endpoint versions.

Marketplace retailers additionally declare a versioned `seller_policy`. A known PDP seller must
exactly resolve to an approved first-party seller to remain eligible. A missing seller is retained
as `seller_unverified` when the Retailer Pack permits it; it is never silently called first-party.
Known non-first-party sellers are removed before matching and reporting with the explicit reason
`known third-party marketplace seller excluded by Retailer Pack policy`. The rule is currently
active for Walmart and Amazon Same Day. Target's policy is defined but remains
`needs_verification` until live Target PDP seller values have been certified. Retailers without a
configured marketplace policy remain eligible and are recorded as `not_governed`.

## PDP and model-assisted evidence

Every distinct in-scope listing is eligible for cached PDP enrichment before final match admission;
noise remains excluded. Search title/attributes may create a provisional candidate before PDP is
available. A same-ID price difference alone does not split product identity. Targeted PDP samples
may be collected for materially different price regimes, but Search remains price authority.

Vision runs only after structured evidence is exhausted: image deduplication, OCR, structured
attribute proposals, source-region provenance, conflict detection, and review. A missing visible
claim is not evidence that the claim is false. Verified structured or human-reviewed evidence
always outranks model inference.

## Reporting contract

The report hierarchy is:

1. **Scoped Product Relationships** — pairwise evidence and local applicability.
2. **Comparable Product Cohorts** — governed Product Pack families such as gallon 2% milk.
3. **Assortment and Whitespace** — local exclusives, missing equivalents, brands, breadth, and gaps.
4. **Product Leadership** — product × benchmark store outcomes against the selected local offer.
5. **Retailer scorecards** — unique-store and product-location rollups with explicit denominators.

Every product, cohort, scorecard, geography, and assortment result links to the same underlying
relationship and local-evidence drawer. Match Review remains the editing surface; reporting
surfaces may confirm/reject only through the same revisioned workflow.

## Implementation phases

### 13.0 — Architecture freeze

- Publish this architecture record, vocabulary, invariants, and release gates.
- Preserve the existing v1 matcher as authoritative.
- Treat the August 3 and August 10 egg inputs as separate versioned datasets and reproduce each
  independently before comparing results.

### 13.1 — Contracts and persistence

- Add schemas for listing identity, trade items, attribute facts, match policies, match edges,
  attribute evidence, match groups, catchments, local comparisons, and coverage reasons.
- Add reversible, additive PostgreSQL tables and indexes.
- Backfill from existing Search and PDP artifacts without paid calls where possible.

### 13.2 — Deterministic evidence and tier engine

- Compile generic tier rules from Product Pack policy.
- Emit matched, conflicting, unknown, and ignored attribute evidence.
- Keep evidence coverage separate from the equivalent-product score.
- Permit overlapping pairwise edges while leaving v1 metric selection unchanged.

### 13.3 — Shadow local comparisons

- Use the same configured 1-, 3-, or 5-mile/service-area graph for candidate applicability and
  Product Leadership.
- Retain all eligible offers and identify the controlling offer deterministically.
- Add local exclusivity, whitespace, and complete coverage-reason projections.
- Reconcile v2 shadow results against v1 without changing production output.

The worker integration is opt-in through `MATCHING_V2_SHADOW_ENABLED` and requires an explicit,
versioned Product Pack `matching_v2` policy. It incrementally collapses positive, in-scope Search
placements to listing evidence, preserves conflicts as unknown, blocks only known hard conflicts,
and writes an immutable per-competitor JSON audit artifact. A Product Pack candidate cap prevents
unbounded pair expansion; shadow errors never modify or fail the authoritative analysis.

### 13.4 — Workbench and reporting

- Add tier, evidence matrix, source provenance, scope, effective dates, alternate matches, and
  revalidation state to Match Workbench.
- Connect report product/cohort/scorecard/assortment drawers to the same contract.
- Replace global assortment match state with local family × store × competitor facts.

The first report-facing surface is deliberately read-only and identified as shadow evidence. It
exposes policy, tier, attribute outcomes, evidence coverage, brand relationship, eligible price
bases, and decision rationale inside the existing Match Workbench.

Phase 13.4 adds a separate protected certification workbench. Its append-only review and
adjudication routes create release evidence only; they do not mutate report matches or make v2
authoritative. See `docs/54_PHASE_13_4_HUMAN_MATCH_CERTIFICATION.md`.

Release certification uses `matching-v2-gold-set.schema.json`. Synthetic fixtures can test the
contract but cannot pass a release gate. Every release label must be adjudicated by at least two
reviewers and cite immutable evidence. Candidate recall and automatic-approval precision are
reported separately overall and by stratum; every automatic approval must have a gold label.

### 13.5 — Bounded AI and vision

- Add OCR/vision attribute proposals, embedding/LLM candidate recall, and exposure-based review
  priority after the deterministic gold set exists.
- Never allow a model-only score to overwrite a governed edge.

The first bounded implementation is user-triggered in Match Certification. It creates a durable,
leased PostgreSQL task, processes it only on the worker that owns the OpenAI credential, and stores
an advisory draft separately from human submissions. Structured evidence is always supplied;
product images are included only when critical structured evidence is incomplete or conflicting.
Every image-derived proposal must cite visible evidence and one of the exact input image URLs.
Drafts always set `authoritative=false` and `human_review_required=true`. A reviewer may explicitly
copy a proposal into their form, edit it, and submit it as their own independent decision. The AI
path cannot certify a match, adjudicate reviewers, change an edge, or update report metrics.

Before any broader AI queue review is enabled, performance must be measured against the independent
human gold set by category and evidence stratum. Model, prompt, schema, input checksum, token usage,
cost, conflicts, and source images remain audit fields.

### 13.6 — Five-category certification and cutover

- Eggs → milk → ground beef → strawberries → bananas.
- Run v1 and v2 in parallel behind a feature flag.
- Promote one Product Pack at a time only after its gates pass.
- Keep historical publications immutable.

## Release gates

- Candidate recall ≥ 99.5% on a stratified human gold set.
- `exact_item` and `exact_specification` automatic precision ≥ 99.9%.
- Zero known hard-attribute conflicts in automatically approved edges.
- `equivalent_product` remains human-approved until separately certified.
- 100% of authoritative edges expose evidence, policy, tier, scope, effective dates, and version.
- 100% of aggregates reconcile to atomic local comparisons.
- Zero duplicate benchmark-store counts in executive scorecards.
- 100% of unscored local contexts have a primary coverage reason.
- Identical evidence and versions produce identical checksums and metrics.
- Governed reanalysis queues zero provider or AI calls.
- Known marketplace sellers outside the active Retailer Pack allowlist contribute zero in-scope
  Search observations, matching candidates, or report metrics; blank sellers remain separately
  countable as unverified.
- Displayed losing-store counts exactly reconcile with their detail/export population.
- Sponsored/organic duplicate placements cannot duplicate product/location price facts.
- Product Pack or engine changes that alter golden results require an explicit documented update.

## Rollback and compatibility

All Phase 13 persistence is additive. V1 tables, Product Pack versions, match revisions, APIs,
analysis results, and publications remain readable. The v2 shadow feature can be disabled without
altering historical results. Destructive cleanup is deferred until every certified category has
completed an agreed retention window.
