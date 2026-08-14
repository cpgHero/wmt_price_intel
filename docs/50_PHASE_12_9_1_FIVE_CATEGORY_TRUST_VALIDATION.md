# Phase 12.9.1 — Five-Category Product-Leadership Trust Validation

## Outcome

Phase 12.9.1 certifies the decision math and evidence chain used by the Competitive Product
Leadership workspaces across fresh ground beef, fresh fluid milk, fresh bananas, fresh
strawberries, and fresh shell eggs. The phase does not add a category branch. It validates the
same canonical Product Location population, governed relationship rules, and deterministic
leadership projector against five materially different Product Packs.

The API now fails closed when an independently recomputed trust certificate disagrees with the
projected result. A report cannot be cached or served with inconsistent summary counts, price-gap
arithmetic, outcome classification, geography rollups, competitor rollups, radius evidence, or
service-area ZIP evidence.

## Source and report inventory

The five release-candidate reports use the complete supplied source files rather than compact
fixtures.

| Category | Historical Search rows | Release-candidate report |
| --- | ---: | --- |
| Fresh bananas | 168,440 | one active five-category report |
| Fresh strawberries | 297,443 | one active five-category report |
| Fresh shell eggs | 386,889 | one active five-category report |
| Fresh fluid milk | 348,980 | one active five-category report |
| Fresh ground beef | 225,791 | one active five-category report |

The report-library row counts and category identities must reconcile to the full-source golden
inputs before a release is accepted.

## Live release-candidate ledger

The production validation used each report's default governed benchmark product, comparison
basis, competitor context, and 3-mile radius. Every row was independently certified by the API
before it reached the UI.

| Category | Observed | Scored | Leader | Tied | At risk | Losing | Unscored | Coverage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Fresh bananas | 4,294 | 2,095 | 0 | 0 | 0 | 2,095 | 2,199 | 48.8% |
| Fresh strawberries | 3,562 | 362 | 362 | 0 | 0 | 0 | 3,200 | 10.2% |
| Fresh shell eggs | 453 | 53 | 23 | 0 | 0 | 30 | 400 | 11.7% |
| Fresh fluid milk | 1,995 | 10 | 0 | 10 | 0 | 0 | 1,985 | 0.5% |
| Fresh ground beef | 4,091 | 2,057 | 0 | 0 | 0 | 2,057 | 2,034 | 50.3% |

Additional evidence checks:

- Milk's ten admitted observations are the ten exact ZIP overlaps in the approved 1,817-location
  relationship scope. Each row is an $11.92-to-$11.92 tie and displays `Same ZIP`, not a fabricated
  distance. North Carolina scopes to 117 observed and ten scored stores; Charlotte scopes to nine
  observed and five scored stores.
- The physical-store radius check is monotonic for the same ground-beef product and denominator:
  1,178 scored stores at 1 mile, 2,057 at 3 miles, and 2,421 at 5 miles.
- Ground beef's 3-mile losses average $0.152 with a $0.25 maximum; the average is calculated from
  all 2,057 scored losses and is not inferred from one display card.
- Eggs reconcile to 23 leaders plus 30 losses; the 30 losses are exact-ZIP Amazon evidence in
  Florida at $6.92 versus $6.49 for the selected pair.
- Strawberries present a truthful zero-loss state and do not name a zero-count competitor or
  market as an insight.
- The production browser emitted no application console errors during the state, city, radius,
  match-group, and store-evidence drill-through.

## Trust defect found and repaired

Distribution-scoped governed relationships store the immutable Search-grain key
`retailer|ZIP|store`. The canonical Product Location contract deliberately uses the portable
location identity `retailer|store|store-id` or `retailer|service_area|ZIP`. Comparing those two
different identifiers caused otherwise valid distribution-scoped relationships to admit no
current observations.

The projector now translates the canonical benchmark observation to the explicit legacy
relationship-scope key only at the relationship-admission boundary. Canonical Product Location
identity is unchanged. The regression covers a benchmark store and an exact-ZIP service-area
competitor so a future key-format change cannot silently remove valid milk or regional-brand
coverage.

## Independent certification

`certify_competitive_product_leadership` is intentionally independent from the production
projector's summary and status helpers. It verifies:

1. unique benchmark-store outcomes and selected product identity;
2. positive, in-stock, Search-authoritative benchmark and competitor prices;
3. declared relationship and retailer-product identity for every scored outcome;
4. price-gap, status-threshold, and reduction-to-lead arithmetic;
5. selected physical-store radius or exact ZIP for service-area retailers;
6. complete observed, scored, leader, tied, at-risk, losing, and unscored reconciliation;
7. coverage, leadership, average-gap, loss-gap, and maximum-loss calculations;
8. state, city, competitor, and filter-count reconciliation; and
9. warnings for unused governed relationships, zero comparable evidence, unresolved brand type,
   and missing imagery.

Any certification error blocks the API response. Warnings remain visible quality work rather than
invented classifications or suppressed evidence.

## Presentation integrity

- A zero scored-store denominator displays an em dash, not a false `0%` leadership score.
- A zero-coverage view explains that no current competitor observation satisfies both the selected
  relationship scope and geographic rule.
- A zero-loss view says no scored benchmark store is currently undercut. It does not name a
  competitor, state, or loss count of zero as an insight.
- Search remains authoritative for location price and observed availability. PDP data remains
  identity and attribute evidence only.

## PDP decision and credit control

Paid PDP calls are allowed for this phase, but are not an acceptance ritual. A call is released
only when all of the following are true:

1. the product survives Product Pack inclusion and appears in a decision-facing relationship or
   unresolved review queue;
2. cached identity evidence cannot answer the specific question;
3. a successful response can materially improve product identity, matching, imagery, brand review,
   or a user-facing decision; and
4. the request uses an observed positive-price Search location for that exact retailer product.

The current five-category replay requires no additional paid PDP request to correct leadership
math. Known unclassified ALDI identity remains a governed review warning because the successful
cached PDP evidence did not provide a usable brand; repeating the same paid request would not make
that classification trustworthy.

## Executed verification

- Five complete-source golden suites: **6 passed** in 422.93 seconds.
- Focused Product Leadership, Product Location, and API regression suites: **17 passed**.
- Local repository suite: **404 passed**, **13 expected integration skips**; the managed desktop
  sandbox alone denied the health test's ephemeral localhost socket bind.
- GitHub CI run `31819718156` passed the unrestricted health test, all Python checks, database
  upgrade/downgrade tests, contracts, TypeScript checks, 46 unit tests, three Playwright tests,
  production builds, and all four application container builds.

## Acceptance commands

```bash
.venv/bin/mypy apps packages/python
.venv/bin/ruff check apps packages/python
.venv/bin/pytest
pnpm contracts:check
pnpm typecheck
pnpm lint
pnpm test
pnpm build
```

Full-source category regressions additionally require all thirteen supplied CSV paths:

```bash
RCI_GOLDEN_GROUND_BEEF_WALMART_CSV=/path/to/Ground_Beef___Walmart_All_Stores_20260807_051643.csv \
RCI_GOLDEN_GROUND_BEEF_ALDI_CSV=/path/to/Ground_Beef___Aldi_All_Stores_20260807_051606.csv \
RCI_GOLDEN_GROUND_BEEF_AMAZON_CSV=/path/to/ground_beef_amazon.csv \
RCI_GOLDEN_MILK_WALMART_CSV=/path/to/Milk___Walmart_All_Stores_20260807_012630.csv \
RCI_GOLDEN_MILK_ALDI_CSV=/path/to/Milk___Aldi_All_Stores_20260807_012605.csv \
RCI_GOLDEN_MILK_AMAZON_CSV=/path/to/milk_amazon.csv \
RCI_GOLDEN_BANANAS_WALMART_CSV=/path/to/Bananas___Walmart_All_Stores_20260807_051626.csv \
RCI_GOLDEN_BANANAS_ALDI_CSV=/path/to/Bananas___Aldi_All_Stores_20260807_051549.csv \
RCI_GOLDEN_BANANAS_AMAZON_CSV=/path/to/bananas_amazon.csv \
RCI_GOLDEN_STRAWBERRIES_WALMART_CSV=/path/to/Strawberries___Walmart_All_Stores_20260807_051705.csv \
RCI_GOLDEN_STRAWBERRIES_ALDI_CSV=/path/to/Strawberries___Aldi_All_Stores_20260807_051534.csv \
RCI_GOLDEN_STRAWBERRIES_AMAZON_CSV=/path/to/strawberries_amazon.csv \
RCI_GOLDEN_EGGS_CSV=/path/to/CCF_Search_Data_08.03.2026_v2.csv \
.venv/bin/pytest \
  packages/python/rci-analytics/tests/test_full_ground_beef_golden.py \
  packages/python/rci-analytics/tests/test_full_milk_golden.py \
  packages/python/rci-analytics/tests/test_full_banana_golden.py \
  packages/python/rci-analytics/tests/test_full_strawberry_golden.py \
  packages/python/rci-analytics/tests/test_full_egg_golden.py
```

## Honest boundary

This phase certifies the current snapshot. Persistence, change, and week-over-week claims remain
disabled until two compatible certified observations exist. Product-specific coverage can be low
without being mathematically wrong; coverage and leadership use different disclosed denominators.
