# Phase 10.3 — Distribution-Scoped Matching and Brand Governance

## Outcome

Phase 10.3 preserves one-to-one product-match integrity at the decision grain where price is
actually compared: a competitor, comparison family, and overlapping primary-retailer store
footprint. A competitor item may correspond to multiple primary-retailer products only when those
primary products have disjoint observed distribution. This supports regional and private-label
milk portfolios without introducing one-to-many arithmetic into a store-level price comparison.

The phase also introduces a Brand Workbench. Product Packs propose private-label, regional, and
national roles, deterministic code describes observed distribution, and a human may confirm,
reject, reset, and explicitly apply an immutable brand-classification revision.

No category-specific condition is added to matching, analytics, API, worker, or UI code. Milk is
the first configured adopter of generic capabilities that other fresh and locally sourced Product
Packs can use.

## Decision grain and invariants

A primary match is unique within:

```text
competitor retailer
× comparison family
× overlapping primary-retailer location scope
```

- A primary or competitor product cannot participate in two primary relationships where those
  scopes overlap in the same comparison family.
- The same competitor product may be reused across disjoint primary-product footprints.
- Alternative relationships may be retained as review evidence but cannot enter authoritative
  price comparisons.
- Unresolved scope intersections fail closed.
- A conflict is excluded rather than silently double-counted.
- Package-price, normalized-unit, and other comparison lenses remain explicit. Scope does not
  convert a package match into a unit-price match or merge their metrics.

The supported scope modes are `global`, `observed_benchmark_product_footprint`, and
`explicit_benchmark_locations`. The default for Milk 1.2.0 is the observed primary-product
footprint at benchmark-store grain. Each scope carries a stable comparison-family key, role,
definition, checksum, source analysis, future-location policy, and optional artifact reference.

Automatic resolution reads this policy directly from each matching profile. It admits reuse when
the complete positive-price Search footprints are disjoint, applies profile priority only among
relationships that overlap, and requires a unique maximum non-conflicting assignment. Equal-rank
overlapping choices remain review candidates and contribute no authoritative price comparisons.
The same generic resolver remains globally one-to-one for Product Packs that do not opt into
scoped reuse.

## Evidence authority

- Search remains authoritative for positive price, availability, ZIP, store, and product
  distribution.
- PDP enrichment remains authoritative only for identity-supporting descriptions,
  specifications, identifiers, URLs, and imagery.
- An observed distribution tier is not a brand classification. A brand with broad presence in
  the current collection is not automatically labeled national.
- Deterministic code owns scope resolution, conflict detection, match admission, metrics, and
  distribution summaries. AI may assist future brand suggestions but cannot confirm a role or
  change an authoritative metric.

New publication context records the complete positive-price Search footprint for each primary
product represented in match candidates. The review service materializes those keys into a
governed decision before persistence. Reanalysis resolves `follow_unique_product_footprint`
against the source evidence without a new provider collection.

## Product Pack configuration

The Product Pack schema adds two generic constructs:

1. `matching_profiles[].relationship_scope_policy` declares the default scope mode, reuse
   permission, relationship role, conflict behavior, comparison context grain, minimum locations,
   and future-location policy.
2. `brand_rules.portfolios` declares stable portfolio IDs, role, retailer applicability, known
   brands, and review policy. `reporting.brand_portfolio_panels` selects configured portfolios for
   future reporting surfaces.

The capability registry exposes the allowed scope modes, roles, context grains, and brand roles.
The loader rejects unknown references, duplicate portfolio IDs, duplicate brand entries within a
retailer/role, and report panels that reference a missing portfolio.

`fresh_fluid_milk` 1.2.0 is a new immutable source version. It configures store-footprint matching
and governed Walmart, ALDI, Amazon, national, and regional portfolios. The earlier 1.1.0 runtime
record remains immutable and historical AnalysisResults stay pinned to it.

## Brand Workbench

The primary application exposes a **Brand Workbench** tab on an analysis. It provides:

- retailer tabs and status/search filters;
- observed products, locations, ZIPs, location share, and distribution tier;
- PDP-backed example imagery when available;
- Product Pack, deterministic, or human origin;
- private-label, regional, national, and unclassified roles;
- confirm, reject, and reset actions; and
- an explicit choice to re-evaluate only the current report or also govern future collections.

Every save creates a new immutable revision with optimistic concurrency and an audit event. Saves
never trigger reanalysis. Reanalysis reuses persisted Search/PDP evidence and queues zero
MetricsCart, PDP, or AI calls. A future-application policy changes only after explicit user
confirmation.

## Match Review changes

The Match Review workbench defaults new decisions to **Primary product footprint** and retains an
explicit **All observed locations** choice. Existing relationships show their scope. Products in
a scoped confirmed relationship remain visible in the manual pool with a relationship indicator,
because they can legitimately participate in another disjoint context. Conflict validation on the
server remains authoritative.

## Persistence and processing

Migration `0024_distribution_scoped_match_governance` adds scope identity to
`product_match_rule`, updates its uniqueness indexes, adds immutable brand revision/rule/event and
future-application tables, and adds `brand_revision_id` to `analysis_run` idempotency.

Worker reanalysis loads exact match and brand revisions. Confirmed brand rules are overlaid on an
in-memory clone of the exact Product Pack; the stored Product Pack is never mutated. A governed
revision disables new AI fallback, preserving reproducibility and ensuring a zero-paid-call
re-evaluation.

## Contracts and routes

Normative schemas:

- `product-match-scope.schema.json`
- `product-footprint.schema.json`
- `scoped-match-assignment.schema.json`
- `brand-classification-decision.schema.json`
- `brand-workbench.schema.json`

Application API:

- `GET /api/v1/analyses/{analysis_id}/brand-workbench`
- `POST /api/v1/analyses/{analysis_id}/brand-workbench/decisions`
- `POST /api/v1/analyses/{analysis_id}/brand-workbench/recompute`
- the existing Match Review decision endpoint accepts an optional scope contract.

## Deferred boundaries

- Explicit map/lasso selection of individual stores is contract- and runtime-ready but is not yet
  exposed as a map editor.
- Brand portfolio scorecards and role-aware narrative are deferred until the primary application
  workflow is accepted.
- HTML, Excel, email, and shareable exports remain intentionally unchanged until primary tabs and
  governance workflows are finalized.
- AI-assisted unknown-brand proposals require a separately approved governed-agent/evaluation
  phase. Phase 10.3 uses Product Pack and deterministic suggestions only.

## Acceptance criteria

- Two primary products may share a competitor product only in disjoint scopes.
- The same pair cannot be duplicated under the same scope checksum.
- Overlapping primary relationships conflict or are excluded before metrics.
- Every location key comes from positive-price Search evidence.
- Human match and brand saves create revisions but do not reanalyze.
- Current-only reanalysis does not alter the future-application policy.
- Future application requires an explicit confirmation.
- Published Product Pack versions remain immutable.
- Milk 1.2.0 behavior is achieved through Product Pack configuration and generic capabilities.
- Reanalysis with governed revisions queues zero paid provider and AI calls.

## Verification commands

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy apps packages/python
uv run alembic -c database/alembic.ini upgrade head
uv run pytest
uv run rci-contracts --root .
pnpm contracts:check
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm test:e2e
```

Production acceptance verifies the migration, the Brand Workbench read/save/reset workflow,
scope-aware conflicting and disjoint decisions, explicit zero-call reanalysis, exact historical
version loading, and primary application light/dark responsive rendering.
