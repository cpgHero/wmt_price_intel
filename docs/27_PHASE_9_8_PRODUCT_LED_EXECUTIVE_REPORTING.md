# Phase 9.8 — Product-led executive reporting

## Outcome

Replace paragraph-heavy, statistically opaque reporting with a product-led decision brief.
The app, HTML attachment, and leadership email continue to use the same governed
AnalysisResult publication.

## Authority boundary

- Search evidence remains authoritative for price, availability, outcomes, and location.
- PDP enrichment supplies product identity, descriptions, package attributes, identifiers,
  URLs, and imagery.
- The deterministic engine selects analysis-admitted product pairs and computes all prices,
  winner outcomes, typical differences, and location evidence.
- The model edits governed evidence into a headline, subtitle, bullets, and action. It cannot
  invent product names or ZIPs; those enter through validated product placeholders.

## Selective PDP rule

PDP candidates are created only from exact-match product pairs admitted into the analysis.
One representative request is planned per retailer product. If the same retailer product has
distinct observed prices across locations, one request is retained per observed price state.
The planner validates required endpoint parameters, prints the exact maximum credit cost, and
does not enqueue work without `--confirm-paid-calls`.

## Decision surface

`product_decisions` ranks exact product pairs into:

- needs attention;
- position to protect;
- price parity.

Each row carries product identities, retailer, typical price difference, comparable-location
count, and the highest-priority ZIP/store evidence. PDP identity is overlaid without changing
the search-derived price facts.

## Verification

```bash
.venv/bin/pytest packages/python/rci-agents/tests/test_governance.py
.venv/bin/pytest packages/python/rci-analytics/tests/test_presentation.py
.venv/bin/pytest packages/python/rci-products/tests
.venv/bin/pytest packages/python/rci-results/tests
.venv/bin/pytest apps/worker/tests/test_analysis.py
.venv/bin/ruff format --check apps packages scripts database
.venv/bin/ruff check apps packages scripts database
.venv/bin/mypy apps packages/python scripts
```

Read-only PDP estimate:

```bash
rci-product-enrichment \
  --analysis-id ANALYSIS_ID \
  --max-product-pairs 16 \
  --max-credits 1000
```

Enqueue only after reviewing the estimate:

```bash
rci-product-enrichment \
  --analysis-id ANALYSIS_ID \
  --max-product-pairs 16 \
  --max-credits 1000 \
  --confirm-paid-calls
```
