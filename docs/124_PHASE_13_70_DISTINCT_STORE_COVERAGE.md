# Phase 13.70 — Distinct Store Coverage Semantics

## Decision

Retailer and Cohort Scorecards present comparison coverage at unique benchmark-location
grain. A benchmark store counts once when at least one eligible certified product
relationship has an admissible competitor Search price under the selected comparison basis,
period, geography, and 1/3/5-mile radius. Multiple products at the same store never inflate
the coverage numerator or denominator.

Physical competitor locations are deduplicated by retailer and provider Store ID. Service-area
retailers such as Amazon Same Day are deduplicated by delivery ZIP and labeled as delivery
areas rather than stores.

## Authoritative metrics

- `benchmark_observed_locations`: distinct benchmark stores carrying at least one in-scope
  benchmark product represented by the scorecard or cohort.
- `benchmark_scored_locations`: distinct benchmark stores with at least one valid local
  comparison.
- `benchmark_unscored_locations`: observed benchmark stores without a valid local comparison.
- `location_coverage_rate`: scored benchmark locations divided by observed benchmark
  locations.
- `competitor_contributing_stores`: distinct physical competitor stores that supplied at least
  one selected local comparison.
- `competitor_contributing_service_areas`: distinct delivery ZIPs that supplied service-area
  evidence.

Product-location counts remain immutable supporting lineage for price outcomes, paired
medians, lower-price share, and downloadable audit evidence. They are no longer presented as
the primary coverage KPI.

## Cohort denominator correction

A cohort retains every observed benchmark store carrying a cohort member even when no
cohort-specific competitor relationship is selected at that store. Such stores are explicitly
unscored for the cohort; they are not dropped from the denominator. Price results continue to
use only admitted cohort relationships.

## Release controls

Competitive Portfolio schema `1.6.0` adds the distinct-location summary. The semantic release
audit requires the fields and verifies:

1. observed benchmark locations equal covered plus uncovered locations;
2. contributing competitor locations equal physical stores plus service areas;
3. the displayed location-coverage rate reconciles exactly to its distinct-store counts; and
4. Assortment and Retailer Scorecards share the same radius-native location summary.

No Search data, PDP evidence, certified relationship, price outcome, or AI decision is changed
by this phase. Existing portfolio materializations must be rebuilt from retained evidence before
the new store-level metrics are published.

## Production acceptance

- Commit `2c8f81a` passed GitHub Actions run `33188271627`, including Python, TypeScript,
  browser, contract, reversible-migration, production-build, and all four container gates.
- Railway API deployment `7ba061f7-514a-4126-b26f-49a48e693351` and web deployment
  `03fbec8b-ed3e-4f35-ac41-2cdef68d4acf` succeeded.
- All 48 configured Competitive Portfolio documents across the six active reports were rebuilt
  from retained evidence as schema `1.6.0` and passed their complete comparison-basis by
  1/3/5-mile semantic gates.
- The live Milk All Brand / ALDI / three-mile scorecard reconciled to 2,273 covered of 4,574
  observed Walmart stores (49.69%) and 1,877 contributing ALDI stores. The materialized API
  returned in 0.23 seconds.
- Switching to five miles changed ALDI to 2,687 of 4,574 Walmart stores (58.75%); Amazon Same
  Day retained same-ZIP service-area coverage as designed. The live browser console was clean.
