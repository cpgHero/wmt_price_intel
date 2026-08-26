# Phase 13.60 — Vitamin Reporting Trust Repair

## Objective

Explain and repair the zero-value retailer scorecards and empty Cohort Scorecard product drawers
in the Spring Valley Vitamins & Supplements publication without changing certified relationships,
Search price, Search availability, PDP source evidence, or audit history.

## Audited publication

- Analysis: `vitamins_supplements-aee8a9d6-33e5-4bac-903c-2570d869db52-match-v2-71792d31`
- Analysis result: `5ea5b275-21f2-489e-b0f1-045ba43a14d0`
- Matching v2 release: `71792d31-4332-4fa3-84c1-a2ce4ea13932`
- Certified identity relationships: 480
- Compatible-specification price-basis relationships: 478
- Default reporting boundary: compatible specification within 3 miles

## Retailer scorecard findings

The zero shown in a retailer scorecard is the count of **scored benchmark product-locations**. It
does not mean the retailer has no certified product relationships.

### Boundary-driven zeros

The only collected physical competitor store for each retailer is outside the default 3-mile
boundary but inside 5 miles:

| Retailer | Certified compatible relationships | Nearest collected competitor store | 3-mile scored product-locations | 5-mile scored product-locations |
| --- | ---: | ---: | ---: | ---: |
| BJ's Wholesale Club | 26 | 4.747 miles | 0 | 13 |
| Meijer | 102 | 3.795 miles | 0 | 32 |
| Sam's Club | 34 | 4.435 miles | 0 | 16 |

These three default zeros are consistent with the configured boundary. The interface should make
the available 5-mile evidence more explicit so a zero cannot be mistaken for missing matches.

### Costco normalized-price defect

Costco has one certified compatible relationship. The priced Costco observation is only 1.580
miles from the relevant Walmart store, so geography does not explain the zero. The classified
Costco row contains the title `Nature Made Extra Strength Vitamin C 500 mg, 180 Gummies`, but its
governed `package_count` is null and `price_per_item` is null. The row is therefore excluded from
the normalized-unit comparison even though the count is visible in the Search title.

### Walgreens boundary plus normalized-price defect

The collected Walgreens store is 4.067 miles from the nearest relevant Walmart store, which
correctly explains the zero at 3 miles. It remains zero at 5 miles because the certified Walgreens
rows also have null `package_count` and null `price_per_item`. Search titles contain usable count
signals such as `300 days`, `100 days`, `90 days`, and `120 days`, but those signals were not
reconciled into governed package-count evidence before the classified price metrics were frozen.

## Cohort drawer defect

The published compatible 3-mile portfolio contains 60 cohort rows, 129 governed relationships,
and non-empty materialized product summaries for every cohort. The empty drawers are therefore
not empty analytical cohorts.

The Cohort Scorecard row is rendered from the radius-native portfolio materialization. On click,
the drawer rebuilds its product list from the older publication `match_candidates` payload. That
helper requires the legacy candidate `matches` value to be greater than zero. A certified
relationship can have zero legacy exact-location matches while contributing scored evidence under
the newer 1/3/5-mile radius engine. The UI then displays a non-zero cohort and an empty drawer
because the row and drawer use different evidence layers.

This was reproduced in production with the Target vitamin-E cohort: the row reports six governed
product pairs and two scored product-locations, while the drawer reports zero included
relationships.

## Pre-repair trust assessment

Before this repair, the vitamin publication was **not decision-ready for these affected cells**:

- BJ's, Meijer, and Sam's Club require clearer radius-boundary disclosure, not match replacement.
- Costco and Walgreens require governed package-count reconciliation and deterministic
  `price_per_item` recomputation.
- Cohort drawers must use the materialized cohort relationship payload rather than legacy
  exact-location candidates.

No certified relationship, source Search row, PDP evidence, or audit lineage was modified during
this diagnostic.

## Implemented repair

### Radius-native cohort lineage

Competitive Portfolio contract `1.3.0` carries the complete certified relationship summaries on
each cohort. Cohort outcomes are now filtered by those exact relationship IDs before rates,
medians, gaps, product rows, and the drill-down payload are calculated. The browser opens the
drawer directly from this immutable radius-native lineage rather than rebuilding identities from
legacy exact-location candidates.

The semantic release gate requires the relationship count and additive outcome counts on every
1.3.0 cohort to reconcile to its relationship rows. Older 1.1/1.2 documents remain readable but
are not accepted as current stored materializations.

### PDP-backed normalized unit recovery

The shared Product Location projector now invokes the existing generic PDP attribute-completion
boundary before calculating Price or Competitive Intelligence observations. It fills only missing
Product Pack attributes, never overwrites known Search/configuration evidence, and then recomputes
only missing derived metrics. Search remains authoritative for package price, positive-price
availability, sponsorship, store, ZIP, and observation time.

The measurement engine recognizes conservative written singular/plural variants declared by a
Product Pack, such as `gummy`/`gummies` and `tablet`/`tablets`. Package-count extraction uses a
bounded PDP identity surface—product name, structured specification/physical/variant fields, and
non-instruction count phrases from the short description—so dosage directions such as “chew two
gummies daily” cannot be mistaken for a two-count package.

A day supply becomes a package count only when two explicit PDP facts agree: the product name
states the number of days and the directions state exactly one tablet, capsule, softgel, or gummy
daily. Multi-unit daily directions remain unresolved. This is a generic evidence rule rather than
a vitamin branch in the core engine.

### Verification and rollout gates

Focused analytics, Product Location, portfolio, release-audit, generated-contract, TypeScript, and
web tests must pass before deployment. Production rollout then rebuilds all exact/compatible
1-, 3-, and 5-mile materializations from retained evidence and verifies:

1. Costco has normalized-unit evidence from its structured `180 Gummies` PDP quantity;
2. Walgreens has normalized-unit evidence only where explicit package or one-unit-daily supply
   facts support it;
3. BJ's, Meijer, and Sam's Club remain honest 3-mile boundary zeros and become scorable at five
   miles where collected local evidence exists;
4. every non-empty cohort drawer contains exactly its governed relationship rows; and
5. the complete six-document semantic audit has zero release-blocking errors.

No MetricsCart, PDP, or OpenAI call is required for the repair or replay.

## Production certification

Production was rematerialized on 2026-08-26 from the retained certified release after API, web,
worker, and scheduler deployment. All six exact/compatible 1-, 3-, and 5-mile documents now use
Competitive Portfolio contract `1.3.0`. The production semantic reconciliation found zero cohort
lineage-count mismatches and zero additive outcome-rollup mismatches.

At the compatible-specification 5-mile boundary, the formerly blank physical-retailer cells now
contain the following scored benchmark product-location evidence:

| Retailer | Certified relationships | Scored product-locations |
| --- | ---: | ---: |
| Meijer | 102 | 32 |
| Sam's Club | 34 | 16 |
| BJ's Wholesale Club | 26 | 13 |
| Walgreens | 11 | 3 |
| Costco | 1 | 1 |

BJ's, Meijer, Sam's Club, and Walgreens remain honest zeros at the 3-mile boundary because their
nearest collected competitor evidence is outside three miles. Costco now scores one relationship
at three miles after PDP-backed recovery of its explicit 180-count package quantity.

Browser verification opened the formerly empty Target 180 mg vitamin-E cohort at compatible
specification / five miles. The row and drawer both contain six governed relationships: two have
selected local price evidence and four remain visible as certified relationships without local
evidence inside the selected radius. This is the intended distinction between match identity and
local price eligibility.

GitHub Actions run `33016471925` passed the complete Python, TypeScript, browser, contract,
migration-cycle, and container-build workflow. Railway API deployment
`9e8e2852-50b6-43f2-897c-707f1dc73bb5`, web deployment
`ac124c7b-e1e4-4f5a-b896-ced35cc8a880`, and worker deployment
`b2a63c56-8b25-4e63-9274-8acd4d21ac68` succeeded. No paid provider call was made.
