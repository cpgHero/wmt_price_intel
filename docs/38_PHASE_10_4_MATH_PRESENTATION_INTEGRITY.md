# Phase 10.4 — Math Presentation Integrity

## Objective

Make every decision-facing number in the primary application self-describing and
reconcilable from the governed `AnalysisResult`, publication context, and linked
Search evidence.

This phase fixes presentation and metric-governance defects found in the
2026-08-11 math-to-UI validation. It does not change authoritative analytical
formulas, Product Pack matching rules, or the deferred HTML/email/XLSX export
design.

## Architectural rules

1. Search observations remain authoritative for store-specific price and
   location evidence. PDP data supplies product identity, imagery, descriptions,
   and attributes only.
2. Every displayed price declares its unit and basis. Package price and a
   normalized price are never presented as the same measure.
3. The median of paired price gaps is named `paired median gap`. It is never
   described as the difference between the two marginal medians.
4. Directional shares always expose the complete mutually exclusive outcome
   set: benchmark lower, competitor lower, and parity.
5. Evidence readiness is calculated from Product Pack minimum-observation and
   minimum-geography rules—not from the existence of one match.
6. Map statistics use the full governed product-decision population. Capped map
   points are explicitly labeled as a deterministic display sample.
7. Renderers consume governed values and metadata; they do not recalculate
   authoritative analytics.
8. A product card may claim a retailer win only when that retailer is lower in
   a majority of matched observations. A plurality without a majority is
   labeled `Mixed price position` and shows all three outcome shares.

## Implementation scope

### Governed contracts and projection

- Extend retailer scorecards with comparison metric, price unit, package basis,
  geography, explicit statistic names, evidence thresholds, and a readiness
  explanation.
- Extend Match Review profile evidence with Search-derived benchmark and
  competitor marginal medians, paired median gap, and price unit.
- Preserve PDP reference price in source enrichment only; do not expose it as a
  price decision signal in Match Review.

### Primary application

- Product cards show normalized or package prices with an explicit unit.
- Product-card status is explained by the directional outcome share; paired
  median gap is supporting evidence rather than a conflicting headline.
- Product cards do not promote a plurality to `Needs attention` or `Position to
  protect`; mixed evidence remains visibly mixed.
- Evidence drawers distinguish the analytical comparison basis from raw
  package prices and expose both when the lens is normalized.
- Retailer scorecards show parity, the selected row basis, evidence thresholds,
  and accurate readiness.
- Geography legends and KPIs use the full governed outcomes, while the plotted
  point count is labeled as a display sample.
- Match Review shows Search-derived relationship price evidence and does not
  label PDP price as a decision reference.

### Regression gates

- Milk per-gallon and eggs per-dozen card/drawer basis tests.
- Full-population versus sampled-map count tests.
- Scorecard parity, basis, statistic, and readiness-threshold tests.
- Match Review Search-price-authority tests.
- Full-source publication replay uses a deterministic bounded quality sampler,
  so large/noisy categories cannot exhaust worker memory before selecting the
  governed evidence sample.
- Contract generation/check, Python tests, web tests, lint, typecheck, and build.

## Acceptance criteria

1. A reader can identify value, unit, comparison basis, statistic, population,
   and evidence threshold without opening methodology.
2. The Organic Valley milk and 24-count egg examples no longer appear to contain
   contradictory prices.
3. Map outcome totals reconcile to the full governed visible product decisions;
   display sampling is disclosed separately.
4. Walmart, competitor, and parity shares reconcile to 100% within stored
   precision.
5. A scorecard below its Product Pack threshold is `Limited evidence` with the
   missing threshold stated.
6. Match Review contains no decision-facing PDP price label.
7. No Product Pack-specific branch is added to the core engine or UI.
8. Tied or split product evidence cannot display a directional win label unless
   one retailer is lower in more than 50% of matched observations.
