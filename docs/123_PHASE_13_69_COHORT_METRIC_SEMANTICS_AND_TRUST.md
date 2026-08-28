# Phase 13.69 — Cohort Metric Semantics and Trust

Date: 2026-08-27  
Status: Implemented; production verification pending

## Incident

The Milk Cohort Scorecard for ALDI, `64 fl oz · whole · organic ·
non-lactose-free`, displayed Walmart and ALDI medians of `$11.92` and `$7.70`
without identifying their unit or observation grain. A reader could reasonably
interpret these as 64-fluid-ounce shelf prices even though the governed Milk
comparison metric is price per gallon.

The brand-neutral profile also contains private-label and national-brand
products in the same specification cohort. The card showed the brand-type mix,
but did not make the profile's brand-neutral eligibility rule or the distinct
product counts sufficiently explicit.

## Evidence reconciliation

- Profile: `all_brand`, displayed as `Specification-equivalent
  (brand-neutral)`.
- Comparison metric: `price_per_gallon`.
- Comparison unit: `USD/gallon`.
- Grain: one scored benchmark product-location, paired with the lowest eligible
  certified local competitor value inside the selected radius.
- Recomputed observations: 7,218.
- Recomputed Walmart median: `$11.92/gallon`.
- Recomputed ALDI selected-local-price median: `$7.70/gallon`.
- Recomputed paired median difference: `-$4.14/gallon`.
- Half-gallon equivalents: approximately `$5.96` and `$3.85` per 64 fluid
  ounces.
- Eight governed product relationships contain eight distinct Walmart products
  and two distinct ALDI products. The Walmart side contains three private-label
  and five national-brand products.

The arithmetic agrees with the underlying certified product-location outcomes.
The defect was semantic presentation, not a corrupt Search price or aggregation
calculation.

## Remediation

1. Cohort rows state the normalized price unit and distinguish the benchmark
   product-location median from the selected local competitor median.
2. When a gallon-normalized cohort has a governed `volume_oz`, the row also
   displays the equivalent price for that package size.
3. Every row states that its median is observation-weighted across scored
   product-locations and is not a package shelf-price median.
4. The historical `all_brand` profile is presented as brand-neutral rather than
   brand-aware; its governed identifier and certified evidence remain unchanged.
5. Brand-type summaries count distinct products, not repeated relationship
   appearances.
6. Competitive portfolio schema 1.5 carries `comparison_metric`,
   `comparison_unit`, and `median_grain` on each cohort.
7. Materialization now fails closed on duplicate cohort scopes and reconciles
   every cohort count, rate, average, and median against the complete scored
   outcomes before persistence.
8. The release audit rejects duplicate cohort identities/scopes, duplicate
   relationship lineage, mixed comparison units, context/profile mismatches,
   missing scored medians, and medians attached to unscored cohorts.

## Cross-publication preflight

The six active publications currently contain 48 profile-by-radius documents
and 1,032 cohort rows. A production preflight found zero duplicate cohort ids,
zero duplicate retailer/profile/segment scopes, zero mixed-unit cohorts, and
zero missing scored medians. Existing semantic audits also report zero errors
for all six publications. Honest evidence-coverage warnings remain warnings and
are not converted into fabricated results.

## Trust boundary

This phase does not change Search prices, certified relationships, Product Pack
attributes, radius eligibility, the lowest-local-price selection rule, or any
price formula. It makes the existing metric legible and adds fail-closed
validation around its publication.

## Production acceptance requirements

- Full Python, contract, TypeScript, build, and browser gates pass.
- All active portfolio documents are rebuilt through schema 1.5 and pass the
  enhanced semantic release audit.
- The Milk ALDI cohort visibly displays `$11.92 per gallon`, approximately
  `$5.96 per 64 fl oz`, two distinct ALDI private-label products, and no duplicate
  ALDI cohort scope.
- Comparison-basis changes and included-product drawers remain responsive.

