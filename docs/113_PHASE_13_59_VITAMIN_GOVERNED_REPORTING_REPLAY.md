# Phase 13.59 — Vitamin Governed Reporting Replay

## Objective

Publish the Spring Valley Vitamins & Supplements analysis from the immutable Matching v2 release
using only the 480 certified relationships. Rejected and insufficient-evidence cases must remain
outside every price calculation, scorecard, cohort, ladder, and product contribution.

## Immutable inputs

- Source shadow: `2026.08.25-spring-valley-brand-shadow-10`
- Search rows: 23,716 across Walmart and nine competitor retailers
- Collection run: `aee8a9d6-33e5-4bac-903c-2570d869db52`
- Matching v2 release: `71792d31-4332-4fa3-84c1-a2ce4ea13932`
- Release checksum: `17b8d5dc3623779c54e230c563897165077b4abcafa81370dfe978478caa9a2d`
- Certified relationships: 480
- Rejected relationships excluded from reporting: 388
- Insufficient-evidence relationships excluded from reporting: 1,448

The source shadow was converted to one immutable input set without recollecting Search data or PDP
data. No MetricsCart or OpenAI call was made.

## Certified identity and price-basis authority

Certification governs whether two retailer products are a valid product relationship. Search
remains authoritative for price and observed location; the analysis engine does not re-decide
certified identity from the weaker Search title.

The 480 certified relationships divide into:

- 130 exact-specification relationships;
- 350 compatible-specification relationships;
- 48 relationships eligible for both package-price and normalized-unit comparisons;
- 430 relationships eligible only for normalized-unit comparison; and
- two certified identity relationships with no approved price basis.

The two relationships without an approved price basis remain visible in the complete certified
identity ledger and assortment lineage. They produce no price fact. This yields exactly 526
confirmed relationship-by-price-basis candidate views and no fallback comparison.

## Radius-native scoring

Physical retailer comparisons are evaluated at the observed Walmart product-store and use the
nearest eligible competitor observation within the selected 1-, 3-, or 5-mile radius. Service-area
retailers use the same delivery ZIP. The scorer selects the lowest positive eligible competitor
price inside the active boundary and never treats a ZIP code as a physical-store match.

The publication materialized six competitive portfolio documents: exact specification and
compatible specification at each of 1, 3, and 5 miles. Relationship identity is certified first;
current local Search evidence determines only whether a price outcome can be scored.

## Production result

- Replay run: `38964433-303f-4507-afe9-460188b83574`
- Result: `5ea5b275-21f2-489e-b0f1-045ba43a14d0`
- Analysis: `vitamins_supplements-aee8a9d6-33e5-4bac-903c-2570d869db52-match-v2-71792d31`
- Publication checksum: `93cd61595ee1267b776cd8c6ae874d463de182877b38e3241709546c46e20268`
- Reporting state: ready
- Materialization state: succeeded

## Trust certification

The release audit reconciled the publication back to its source and certification boundaries:

- 480 expected and 480 retained certified relationships;
- zero missing certified relationships;
- zero invented relationships;
- 526 expected and 526 confirmed relationship-by-price-basis candidates;
- zero fallback candidates;
- zero rejected or insufficient-evidence cases in price reporting; and
- all 23,716 source rows bound to the immutable collection input.

The semantic publication gate passed with zero errors and 68 explicit warnings. The warnings are
not calculation failures. They disclose selected retailer/radius/basis cells without scorable local
price overlap, certified relationships excluded from cohorts because governed cohort attributes are
incomplete, and exact-specification views where no such relationship was certified.

## Verification

The full Python suite passed 764 tests with 16 environment-dependent skips. Python static typing
passed across 151 source files. Focused worker regression tests passed after adding the two
certified-relationship edge cases. The live application read-through confirmed the report route,
radius and comparison-basis controls, retailer scorecards, explicit local-evidence zero states, and
the absence of a server-error state. The interface distinguishes the complete 480-relationship
identity ledger from the 478 relationships eligible for the selected compatible price basis.

