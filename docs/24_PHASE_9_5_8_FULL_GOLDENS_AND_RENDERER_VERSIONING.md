# Phase 9.5.8 — Full Goldens and Renderer Versioning

## Outcome

Phase 9.5.8 closes the milk and banana reference-output gaps without adding category branches to
the core engine. It also makes rendered report artifacts immutable by renderer version, so a new
presentation release can coexist with prior HTML, workbook, email, and audit-package outputs.

No live MetricsCart credit is required for this phase. The full regressions use the user-supplied
August 2026 exports, and the Product Packs use the supplied reference workbooks as validated catalog
evidence.

## Product Pack approach

Milk and banana behavior remains data-driven:

- Known product IDs have explicit scope and attribute decisions in Product Pack retailer catalogs.
- Deterministic extraction rules remain the fallback for newly observed products.
- An explicit catalog inclusion may override a broad text exclusion because the curated decision is
  higher-quality evidence for that product ID.
- Milk profiles compare a configured gallon-equivalent metric and apply profile-specific brand
  policy and role constraints.
- Banana profiles encode each, weight, package, midpoint, and 4–5 count range interpretations. The
  range profile records low/high interval evidence rather than hiding the uncertainty in a single
  guessed value.

The reusable core additions are retailer-product-ID extraction, role-specific attribute
constraints, and optional comparison intervals. None inspects a category, Product Pack ID, title,
or category-specific attribute name.

Historical observation timestamps are normalized to UTC RFC 3339 before V2 provenance assembly.
The same generic normalizer accepts timezone-aware or timezone-naive ISO values and Unix seconds,
milliseconds, microseconds, or nanoseconds (including scientific notation); malformed values are
treated as missing rather than emitted as invalid contract datetimes.

## Permanent full-data gates

`test_full_milk_golden.py` streams 348,980 rows through normalization, classification, reduction,
and comparison. It asserts the reference source totals, qualifying rows, distinct products,
ZIP/store coverage, and all six retailer/mode comparison summaries.

`test_full_banana_golden.py` streams 168,440 rows through the same generic pipeline. It asserts the
reference source totals, qualifying rows, distinct products, ZIP/store coverage, and all ten
comparison summaries. The 811 conventional 4–5 count bunch matches must retain interval endpoints
that contain the compared Walmart each price.

The product catalogs stored under `fixtures/golden/milk/` and `fixtures/golden/bananas/` contain
validated classification evidence only. Raw retailer exports remain external because of their size
and provenance.

## Renderer identity and migration

Renderer release `2.0.0` is part of every artifact payload, database record, object-storage key,
API response, audit event, and audit manifest. Artifact cache lookup requires both artifact type and
renderer version. Re-rendering with a future version therefore produces a distinct immutable object
without overwriting the prior version.

Migration `0014_report_renderer_versions`:

1. Adds `report_artifact.renderer_version` with a `legacy` default.
2. Backfills the newest pre-migration artifact for each analysis/type as `legacy` and preserves any
   historical duplicates with stable `legacy-<artifact-id>` identities.
3. Makes the column non-null.
4. Replaces the prior artifact identity constraint with
   `(analysis_run_id, artifact_type, renderer_version)`.

## Exact acceptance commands

```bash
RCI_GOLDEN_MILK_WALMART_CSV=/path/to/Milk___Walmart_All_Stores_20260807_012630.csv \
RCI_GOLDEN_MILK_ALDI_CSV=/path/to/Milk___Aldi_All_Stores_20260807_012605.csv \
RCI_GOLDEN_MILK_AMAZON_CSV=/path/to/milk_amazon.csv \
uv run pytest packages/python/rci-analytics/tests/test_full_milk_golden.py

RCI_GOLDEN_BANANAS_WALMART_CSV=/path/to/Bananas___Walmart_All_Stores_20260807_051626.csv \
RCI_GOLDEN_BANANAS_ALDI_CSV=/path/to/Bananas___Aldi_All_Stores_20260807_051549.csv \
RCI_GOLDEN_BANANAS_AMAZON_CSV=/path/to/bananas_amazon.csv \
uv run pytest packages/python/rci-analytics/tests/test_full_banana_golden.py

uv run pytest
uv run ruff format --check apps packages scripts database
uv run ruff check apps packages scripts database
uv run mypy apps packages/python scripts
uv run alembic -c database/alembic.ini upgrade head --sql
pnpm contracts:check
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm test:e2e
```

A paid live Search/PDP smoke test remains separately governed. It is not an implicit deployment or
phase-acceptance step.

## Production acceptance — 2026-08-09

Railway deployed implementation commit `5d28f41` and historical timestamp-normalization commit
`3a7a1c4`. The API pre-deploy command upgraded production from migration `0013` through
`0014_report_renderer_versions`; the web, API, worker, and scheduler deployments completed
successfully.

The approved, zero-credit historical replay processed the complete August 7 ground-beef source set:

- Analysis ID:
  `fresh_ground_beef-940c8d6a-7990-4a5d-a58f-c0fd02fb872f`
- Analysis run ID: `524f8850-37f4-4bc2-ac5f-7af15dcd18f8`
- Collection run ID: `940c8d6a-7990-4a5d-a58f-c0fd02fb872f`
- Input set ID: `810c2791-aa78-4c16-85ab-c5fe31b1d308`
- Source rows: 225,791
- Analysis contract: `2.0.0`
- Validation: `ready_to_share`
- Result contents: 457 metrics, 49 comparisons, 10 insights, and 10 recommendations
- Final result checksum:
  `c32f5d1c70a539fb39590c82966fc7757005fe46659f1957cd90e33f4c28be1a`

The first replay exposed two source timestamp encodings that were valid historical evidence but
not valid JSON Schema `date-time` strings. The category-neutral normalizer documented above was
added and fully regression-tested before the successful replay. No source row, analytical rule, or
Product Pack exception was introduced to work around the issue.

Production generated HTML, XLSX, leadership-email, and audit-ZIP artifacts with renderer version
`2.0.0`. Browser acceptance covered every analysis workspace section, all four export controls, and
light/dark theme switching at:

<https://web-production-ee2a4.up.railway.app/analyses/fresh_ground_beef-940c8d6a-7990-4a5d-a58f-c0fd02fb872f>

Historical replay was returned to disabled after completion. No live Search or PDP request was made,
so this acceptance consumed zero billable MetricsCart credits.
