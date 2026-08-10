# Phase 9.7 — Decision Surface and Selective Enrichment

## Status

Implemented and under production acceptance. This phase changes presentation and future PDP
planning without collecting new MetricsCart data.

## Decision surface

The app workspace and downloadable HTML report use the same report projection. Generic source-row,
ZIP-count, and match-count cards are no longer presented as decision KPIs.

- **Competitive scorecard:** strict exact-ZIP package-price outcomes, matched geographies, price
  position, average gap, and win/parity rates by competitor.
- **Comparable-market coverage:** matched geographies by competitor, rather than raw retailer
  footprint counts that do not establish comparability.
- **Benchmark-product price map:** evidence-linked exact-match locations filterable by benchmark
  product. Each point carries the benchmark product ID and name, competitor, outcome, ZIP, store,
  both observed prices, and signed price gap.
- **Bounded browser payload:** at most 20 benchmark products and 150 geographically distributed
  points per product. Selection is deterministic and does not change analytical results.

Map presentation context is immutable and publication-scoped. New analyses generate it
automatically. Existing historical analyses can be replayed from stored source artifacts to create
a new publication and report artifact without changing the immutable AnalysisResult.

## PDP selection contract

Product Details enrichment is downstream of analytical admission:

1. Build the explicit set of offer IDs retained for analysis from classified and matched evidence.
2. Exclude all other search-result rows; search noise cannot consume PDP credits.
3. Group admitted offers by retailer and retailer product ID.
4. Select one deterministic representative location per product.
5. If that product ID has multiple observed package prices, select one representative location for
   each distinct price state. This is the only location fan-out.
6. Use the existing cache, durable queue, budget, rate-limit, lease, retry, and idempotency controls.

Search evidence remains authoritative for price and availability. PDP evidence supplies identity,
descriptions, images, identifiers, taxonomy, and package semantics. It may flag a possible variant
but never rewrites an observed search price.

## Radius profiles

The existing 10-mile results remain unchanged for reproducibility. A later Product Pack revision
will add governed 1-, 3-, and 5-mile comparison profiles, schema validation, labels, and golden
benchmarks. The core engine already supports generic radius profiles, so this change must remain
configuration-led and must not add category branches.

## Acceptance commands

```bash
uv run pytest packages/python/rci-products/tests/test_planning.py
uv run pytest packages/python/rci-analytics/tests/test_presentation.py
uv run pytest apps/worker/tests/test_analysis.py
uv run pytest packages/python/rci-results/tests
uv run ruff format --check .
uv run ruff check .
uv run mypy apps packages/python
pnpm --filter @rci/web test
pnpm --filter @rci/web typecheck
pnpm --filter @rci/web lint
pnpm --filter @rci/web build
```

The publication-context replay command performs zero OpenAI calls and zero MetricsCart calls.
