# Test and Golden Regression Strategy

## Layers

1. JSON Schema contract tests.
2. Price/ID/ZIP parsing unit tests.
3. API result-array extraction tests for all supported nesting paths.
4. Walmart/ALDI/Amazon adapter normalization tests against supplied response fixtures.
5. Location master import tests.
6. Queue concurrency and lease recovery tests.
7. Shared rate limiter/429 cooldown tests.
8. Product Pack rule tests.
9. Compact category fixture tests.
10. Full golden regression tests using the original August 2026 datasets.
11. Cron/timezone, schedule-slot idempotency, budget-window, historical comparison, alert evidence,
    cooldown, and email retry tests.
12. PostgreSQL multi-claimer integration tests for schedules, analysis evaluation, and email delivery.

## Golden rule

A change that materially changes a golden metric is not automatically a bug, but it must not be merged silently. The pull request must state:
- which benchmark changed,
- old/new value,
- reason,
- evidence that new behavior is more correct,
- Product Pack or engine version change.

## First acceptance dataset

Strawberries: 297,443 source rows in validated run. Headline assertions are in `fixtures/golden/benchmarks.json` and detailed expected summary files are under `fixtures/golden/strawberries/`.

## Matching Architecture v2 certification

Matching v2 uses a separate, human-adjudicated pair-label gold set; aggregate price-report goldens
cannot substitute for match labels. A release set must validate against
`schemas/matching-v2-gold-set.schema.json`, cite immutable Search/PDP evidence, and record at least
two reviewers per label. Certification reports candidate recall separately from automatic-tier
precision, includes per-stratum metrics, fails any unlabeled automatic approval, and does not permit
synthetic contract fixtures to claim release readiness. The five-category order is eggs, milk,
ground beef, strawberries, then bananas.

The Phase 13.4 evidence profiler and review-queue tests are run with:

```bash
uv run pytest packages/python/rci-analytics/tests/test_matching_v2.py \
  packages/python/rci-contracts/tests/test_validator.py \
  apps/api/tests/test_matching_v2_review.py
```

Full-data evidence results and the human certification workflow are documented in
`docs/54_PHASE_13_4_HUMAN_MATCH_CERTIFICATION.md`.

## Regression sequence

Strawberries -> Eggs -> Milk -> Bananas.

This order intentionally exercises different abstraction pressures: package weight, categorical claims/counts, volume/specialty/same-brand/private-label modes, and each-vs-weight/bunch normalization.

## Phase 8 executable gates

Run the configuration-driven vertical slices and core-path audit:

```bash
uv run pytest packages/python/rci-analytics/tests/test_product_pack_abstraction.py
```

Reconcile every compact benchmark shipped in the handoff:

```bash
uv run python scripts/validate_handoff.py
```

Run the attached full strawberry baseline:

```bash
RCI_GOLDEN_STRAWBERRIES_WALMART_CSV=/path/to/Strawberries___Walmart_All_Stores_20260807_051705.csv \
RCI_GOLDEN_STRAWBERRIES_ALDI_CSV=/path/to/Strawberries___Aldi_All_Stores_20260807_051534.csv \
RCI_GOLDEN_STRAWBERRIES_AMAZON_CSV=/path/to/strawberries_amazon.csv \
uv run pytest packages/python/rci-analytics/tests/test_full_strawberry_golden.py
```

Run the attached consolidated egg baseline:

```bash
RCI_GOLDEN_EGGS_CSV=/path/to/CCF_Search_Data_08.03.2026_v2.csv \
uv run pytest packages/python/rci-analytics/tests/test_full_egg_golden.py
```

The egg gate validates all 386,889 export rows and 14 retailer identities against the
human-validated catalog, then replays all 5,155 validated strict matches through the generic
comparison engine. The export's common columns are deliberately not used as MetricsCart API
adapter fixtures.

Run the attached full milk baseline:

```bash
RCI_GOLDEN_MILK_WALMART_CSV=/path/to/Milk___Walmart_All_Stores_20260807_012630.csv \
RCI_GOLDEN_MILK_ALDI_CSV=/path/to/Milk___Aldi_All_Stores_20260807_012605.csv \
RCI_GOLDEN_MILK_AMAZON_CSV=/path/to/milk_amazon.csv \
uv run pytest packages/python/rci-analytics/tests/test_full_milk_golden.py
```

Run the attached full banana baseline:

```bash
RCI_GOLDEN_BANANAS_WALMART_CSV=/path/to/Bananas___Walmart_All_Stores_20260807_051626.csv \
RCI_GOLDEN_BANANAS_ALDI_CSV=/path/to/Bananas___Aldi_All_Stores_20260807_051549.csv \
RCI_GOLDEN_BANANAS_AMAZON_CSV=/path/to/bananas_amazon.csv \
uv run pytest packages/python/rci-analytics/tests/test_full_banana_golden.py
```

The milk gate reconciles all 348,980 rows, source/retailer coverage, and six comparison modes. The
banana gate reconciles all 168,440 rows, source/retailer coverage, and ten comparison rows,
including an evidence-preserving range comparison for 4–5 count bunches.

## Phase 9 executable gates

```bash
uv run pytest packages/python/rci-automation/tests apps/api/tests/test_automation.py
uv run pytest
uv run ruff format --check apps packages scripts database
uv run ruff check apps packages scripts database
uv run mypy apps packages/python scripts
pnpm contracts:check
pnpm lint && pnpm typecheck && pnpm test && pnpm build && pnpm test:e2e
```

Set `RCI_TEST_DATABASE_URL` to a disposable migrated PostgreSQL database to run the exclusive-claim
integration cases; CI supplies this automatically.
