# Phase 9.5 — Decision-Grade Analysis and Reporting Parity

## Status

Approved implementation scope. This document is the acceptance specification for Phase 9.5.
Subphases must be completed in order. A later subphase must not weaken an earlier contract or
golden gate without a documented benchmark revision.

## Objective

Close the gap between the current vertical-slice output and the five human-validated reference
analyses while preserving the architecture invariants in `AGENTS.md`.

The target is one deterministic engine, versioned Product Packs, optional PDP enrichment,
bounded role-oriented AI, one canonical AnalysisResult, and evidence-backed UI/HTML/Excel/email
delivery.

## Normative Phase 9.5 contracts

The V1 contracts remain active until the historical replay migration is complete. Phase 9.5 adds
the following contracts without silently changing existing runtime behavior:

| Contract | Responsibility |
|---|---|
| `analysis-result-v2.schema.json` | Canonical metrics, insights, narratives, evidence references, and provenance |
| `analysis-evidence.schema.json` | Immutable Parquet/JSON evidence-set manifest |
| `canonical-product.schema.json` | Retailer product identity and source-context linkage |
| `product-detail-snapshot.schema.json` | Versioned MetricsCart PDP request, billing, normalized fields, and raw artifact |
| `agent-output.schema.json` | Bounded classification, comparison-QA, insight, and narrative outputs |
| `report-blueprint.schema.json` | Product Pack-driven sections, artifacts, worksheets, and narrative policy |

The schemas are shared across Python and TypeScript through generated types and repository-wide
contract validation.

## Source authority

1. The collected or imported SERP snapshot is authoritative for observed price, availability,
   retailer, ZIP, store, fulfillment context, and collection time.
2. PDP snapshots are authoritative for product identity and may validate package semantics.
3. PDP price or availability must not overwrite the corresponding SERP observation in an
   analysis of that snapshot.
4. Web or manual research may validate ambiguous semantics but cannot replace historical prices.
5. Every raw source and derived evidence set is immutable and checksummed.

## Analytical authority

Deterministic code exclusively owns counts, denominators, prices, medians, rates, unit
conversions, distances, match eligibility, and golden assertions.

AI may interpret only the evidence supplied to its role. Every AI-produced insight or narrative
section must carry metric and evidence references. `authoritative_metrics_computed` is always
false. Publication fails when unsupported numeric claims are nonzero or metric-reference
coverage is below 100 percent.

## AnalysisResult V2 design

Authoritative numeric facts live in the top-level `metrics` collection. Coverage, segments,
comparisons, geographic sensitivity, insights, recommendations, and narratives refer to those
metric IDs and to immutable evidence-set IDs.

Large row-level datasets do not live inline in JSONB. They are stored as private immutable
Parquet/JSON artifacts represented by `analysis-evidence.schema.json`.

V2 supports either:

- a live `collection_run`, or
- a checksummed `historical_import` input set.

This permits the complete August 2026 datasets to exercise the same analysis pipeline as future
scheduled collections.

## Product identity and PDP rules

- Retailer product IDs, ASINs, UPCs, GTINs, store IDs, and ZIP codes are strings.
- A canonical product belongs to one retailer and retailer product ID.
- Alternate identifiers are retained rather than collapsed into one guessed ID.
- PDP cache identity includes retailer, product ID, ZIP, store, fulfillment, and endpoint version.
- Stable identity fields and contextual observations are stored separately.
- Complete provider responses remain in private raw storage; normalized snapshots contain only
  contracted fields and raw-artifact provenance.

## Reporting rules

Product Packs select a versioned report blueprint. The blueprint determines which sections,
metrics, evidence kinds, visualizations, workbook sheets, caveats, and narrative questions are
required.

The same AnalysisResult and evidence sets feed the web workspace, HTML, Excel, leadership email,
and audit ZIP. Renderers must not import the analytics engine or recalculate facts.

## Product Pack onboarding acceptance

A new category follows this repeatable sequence:

1. Profile representative SERP results.
2. Define scope, exclusions, attributes, units, and ambiguous semantics.
3. Configure generic extractors and matching profiles.
4. Capture a small budgeted PDP fixture set when needed.
5. Add labeled classification and comparison-QA examples.
6. Define headline segments, insight rules, report blueprint, and caveats.
7. Add compact and full golden assertions.
8. Publish an immutable Product Pack version.

The category cannot be activated until the contract, classification, matching, full-golden,
report, and no-category-branch gates pass.

## Five-category acceptance matrix

| Category | Source rows | Required abstraction behavior |
|---|---:|---|
| Fresh shell eggs | 386,889 | Count/size/grade/housing, strict and relaxed, price per dozen, 14 retailers |
| Fresh fluid milk | 348,980 | Same-brand/private-label/equivalent, specialty claims, price per gallon |
| Fresh bananas | 168,440 | Each/bunch/weight ambiguity and organic package reversal |
| Fresh strawberries | 297,443 | Exact weight, price per pound, no fabricated per-berry metric, 10-mile validation |
| Fresh ground beef | 225,791 | Lean ratio, variable package weight, price per pound, 10-mile validation |

Ground-beef headline assertions are executable in `fixtures/golden/benchmarks.json` and include:

- 3,823 Walmart qualifying ZIPs;
- 9,049 ALDI exact matches;
- 84.14189413 percent ALDI competitor-lower rate;
- 6,713 Amazon exact matches;
- 93.63920751 percent Walmart-lower rate against Amazon;
- 16,985 ALDI 10-mile matches;
- an approximately $1.48/lb ALDI advantage for organic grass-fed 85/15.

## MetricsCart development budget

The approved bank is at most 1,000 billable credits. Phase 9.5 uses historical files for
full-location testing.

- Initial live fixture capture target: 15 credits.
- Initial fixture retry ceiling: 30 credits.
- HTTP 200 and 404 are billable according to the endpoint catalog.
- Other statuses are nonbillable.
- No live provider calls occur in CI.
- Every live smoke test requires an explicit run budget and writes an auditable credit ledger.

## Phase gates

### 9.5.1 Contracts and acceptance specification

- All six new schemas validate their examples in Python and TypeScript.
- Generated TypeScript types are committed and clean.
- The fifth golden benchmark is executable.
- Existing V1 examples and runtime tests remain unchanged and passing.

### 9.5.2 Historical import and replay

- Checksummed input sets support live collections and historical files.
- Import is idempotent and preserves source row counts and identifiers.
- Strawberry and ground-beef historical inputs can reach the generic analysis queue.

Implementation contract: `historical-input-manifest.schema.json`. Operational details and pinned
full-source manifests are documented in `docs/18_PHASE_9_5_2_HISTORICAL_REPLAY.md`.

### 9.5.3 Generic analytics and ground-beef Product Pack

- Ground beef passes full-source headline assertions.
- Variable-weight ALDI package totals are normalized without changing source price.
- No `ground_beef` category branch exists in generic runtime modules.

### 9.5.4 Product identity and PDP enrichment

- Walmart, ALDI, and Amazon fixtures normalize successfully.
- One cached PDP snapshot can enrich all linked SERP observations.
- Shared rate/cooldown and credit ceilings remain correct across replicas.

### 9.5.5 Insight and reporting engine

- Deterministic insight candidates rank breadth, magnitude, confidence, and actionability.
- Product Pack report blueprints drive UI and artifact sections.
- Renderers remain analytics-free.

### 9.5.6 Governed AI agents

- AI cannot write authoritative metric fields.
- Every numeric narrative claim resolves to a deterministic metric.
- Unsupported numeric claims equal zero.
- Metric-reference coverage equals 100 percent.

### 9.5.7 Branded UI and artifacts

- CPGHero light/dark tokens apply to the application shell.
- Analysis workspace includes summary, geography, price, segments, products, opportunities,
  quality, and methodology.
- HTML, Excel, email, and audit artifacts reconcile to the same result checksum.

### 9.5.8 Full golden and Railway acceptance

- All five full-source regressions pass.
- Contract, lint, type, unit, integration, browser, migration, concurrency, and live smoke gates
  pass.
- Railway web, API, worker, scheduler, Postgres, and bucket remain healthy.

## Commands

```bash
make check
```

```bash
uv run python scripts/validate_handoff.py
```

```bash
uv run pytest packages/python/rci-analytics/tests/test_product_pack_abstraction.py
```

Full-source commands remain opt-in through the documented `RCI_GOLDEN_*` environment variables.
