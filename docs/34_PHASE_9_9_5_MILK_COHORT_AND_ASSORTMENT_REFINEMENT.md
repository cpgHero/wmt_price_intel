# Phase 9.9.5 — Milk Cohort and Assortment Refinement

## Decision

High-cardinality milk assortment does not change product-match cardinality. A decision-ready
product relationship remains one benchmark product to one competitor product within every eligible
comparison lens. Broader analysis is provided through Product Pack cohorts and Search-derived
assortment rollups.

The implementation is category-neutral. Milk exercises the capabilities because it contains a
large regional brand and package mix; no core module branches on the milk Product Pack ID.

## Comparison hierarchy

1. **Item relationship** — one-to-one, governed, auditable, and linked to store-specific Search
   evidence.
2. **Comparable cohort** — multiple admitted one-to-one relationships summarized using the Product
   Pack's headline dimensions. Cohorts never create a cross-product of candidate products.
3. **Assortment rollup** — distinct product, brand, ZIP, and location breadth. Unmatched products and
   geographically concentrated brands are review signals, not assumed substitutes or proven local
   distribution.

## Implemented refinement

### Price and cohorts

- The report projector now emits machine-readable numeric comparison values alongside existing
  formatted display fields. The web renderer sorts and filters those persisted values; it does not
  recompute rates, medians, gaps, winners, or denominators.
- The report view exposes the Product Pack headline cohort dimensions and its minimum-geography
  decision threshold.
- Price & Segments now includes an interactive cohort explorer with:
  - global competitor and comparison-lens scoping;
  - benchmark-lower, competitor-lower, and parity filters;
  - ranking by evidence breadth, competitor pressure, or absolute typical gap;
  - separate lower-price shares, retailer medians, matched observations, and matched ZIP markets;
  - explicit limited-evidence labeling below the Product Pack threshold; and
  - a direct path to governed item-relationship review.

### Match review

- Ambiguous candidates sort ahead of suggested, confirmed, and rejected relationships.
- Ambiguous candidates are then ranked by matched-geography breadth, retained observations, and
  absolute price-gap magnitude.
- A dedicated callout filters directly to the needs-decision queue.
- Confirm, reject, reset, staged revisions, explicit re-evaluation, and future-run application remain
  unchanged.

### Assortment

- Terminology now distinguishes one-to-one item relationships, comparable cohorts, and assortment
  rollups.
- Retailer summaries include observed brand count, unbranded product count, top brands by location
  breadth, and geographically concentrated brand signals.
- Geographic concentration means a brand was observed in at least two locations and no more than
  25% of the retailer's collected locations. It is not labeled as a proven local brand.
- Shared-ZIP drilldowns identify the largest primary-retailer and competitor product-count gaps.
- Ambiguous candidate-group counts are visible beside relationship and whitespace measures.
- Search remains authoritative for assortment presence, store/ZIP breadth, and price. PDP remains
  identity and imagery enrichment only.

## PDP cadence boundary

This phase does not trigger new PDP calls and does not silently change cache policy. Current identity
snapshots remain reusable through the governed Product Details cache. A future collection-control
phase may expose separate user-configurable policies for new/changed products, priority products,
stable products, and manual credit-capped refreshes. Price evidence remains collection-cadence Search
data regardless of PDP cadence.

## Validation

```bash
pnpm contracts:check
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
uv run ruff check .
uv run mypy apps packages/python
uv run pytest
pnpm build
pnpm test:e2e
```

Focused local acceptance completed during implementation:

- report-contract validation: 31 normative JSON documents;
- Python: 294 passed, 12 environment-gated integration/golden tests skipped locally;
- web unit tests: 29 passed;
- production Next.js build: passed;
- focused Python assortment and projector tests: 26 passed;
- focused cohort and match-review TypeScript tests: 9 passed.

Production publication-context replay for milk must use persisted historical inputs and cached PDP
identity only. It makes zero MetricsCart calls and zero OpenAI calls.

## Acceptance criteria

1. A milk product cannot be confirmed against more than one competitor product for the same governed
   relationship scope.
2. Cohort cards reproduce persisted comparison metrics exactly and never calculate new analytical
   outcomes in TypeScript.
3. A user can distinguish item relationships, comparable cohorts, and assortment rollups without
   reading methodology documentation.
4. Low-evidence cohorts are visibly labeled using the Product Pack threshold.
5. Ambiguous candidates are excluded from decision-ready reporting and appear first in Match Review.
6. Brand concentration and ZIP breadth drilldowns trace to Search-derived assortment observations.
7. Light and dark modes remain usable on desktop and mobile layouts.
8. No Product Pack ID or product-category branch exists in generic analytics, reporting, or UI code.

## Blocking questions

None.
