# Phase 13.23 — Scorecard Presentation and Brand Evidence Reconciliation

Status: deployed and production-verified

## Purpose

Restore the proven Retailer Scorecard presentation after the radius-native data cutover, make
included-product evidence readable and auditable, explain the distinct aggregation levels on
Cohort Scorecards, and reconcile every assortment brand card to the complete governed product list.

## Authority boundary

This phase changes presentation and evidence joins only. It does not change product matching,
comparison eligibility, distance calculations, price authority, denominators, rates, averages,
certification decisions, or immutable source evidence. Retailer and cohort results continue to come
from pre-materialized certified product-location outcomes for the selected retailer, comparison
basis, geography, and 1/3/5-mile radius. Service-area retailers retain the explicitly labeled same
delivery-ZIP rule.

## Retailer Scorecards

The dense retailer scorecard table is restored with five decision-oriented columns:

- competitor and active comparison context;
- comparable evidence and included-product drill-through;
- mutually exclusive Walmart-lower, competitor-lower, and parity shares;
- plain-language average local price position; and
- comparable-evidence status and local coverage.

The included-products drawer uses bounded product imagery, wrapping product names, product IDs,
relationship counts, scored and observed product-location counts, local price position, search, and
progressive disclosure. The displayed product count is the exact length of the contributing product
list supplied by the radius-native API.

## Cohort Scorecards

The page now distinguishes two related but non-duplicative aggregation levels:

1. **Price Position Table** — one retailer-level result across all eligible certified
   product-locations in the selected context. It answers who is lower overall and the evidence
   coverage behind that result.
2. **Segment Drivers and Reversals** — the same certified evidence partitioned by governed Product
   Pack attributes. It identifies which comparable cohorts create, weaken, or reverse the overall
   result.

The legacy blueprint versions of those tables are suppressed on this workspace because they used a
different historical aggregation context. Both current radius-native views download to CSV and
Excel.

## Assortment brand evidence

Brand scorecards are calculated from the governed Search assortment identity. PDP may later enrich
the product's display brand, but that label cannot change membership in an already calculated brand
row. The compact interactive read model therefore retains `observed_brand` from the governed Search
attributes alongside the PDP-enriched `brand`.

Observed Brand Breadth opens a searchable list of every brand, not only the top twelve. Selecting
any leading or geographically concentrated brand uses the same normalized `observed_brand` identity
to return every contributing product. The drawer explicitly reports the reconciled product count and
links each product to its Price Intelligence footprint.

## Lifecycle and cost

- No MetricsCart or OpenAI calls are required.
- No report, raw Search/PDP artifact, match certification, or audit record is archived or deleted.
- Existing immutable publications remain intact; the API regenerates the compact interactive read
  view from their retained presentation context.

## Verification plan

- Python renderer regression proving Search brand identity survives PDP display-brand enrichment.
- TypeScript unit regression proving brand-product membership follows `observed_brand`.
- Web unit, type, lint, production-build, contract, and browser suites.
- Live Egg walkthrough of Retailer Scorecards, both Cohort Scorecard downloads, the complete brand
  list, and at least one brand whose Search and PDP labels differ.

## Production verification

- GitHub Actions run `32420363332` passed the full Python, contract, migration, TypeScript, build,
  and 13-test browser suite for the final governed-brand membership correction.
- The live included-products drawer renders 58-by-58-pixel product images with no measured
  horizontal overflow at a 980-pixel drawer width.
- The live Cohort Scorecards page exposes both the overall Price Position Table and the diagnostic
  Segment Drivers and Reversals view, with CSV and Excel controls for each.
- The live Egg report exposes all 43 Walmart brands in its searchable brand directory. A complete
  API reconciliation checked 161 retailer-brand rows and found zero count-to-product-membership
  mismatches.
- The historical Hillandale Farms edge case now displays one governed Search product in both the
  brand scorecard and its drawer. The second PDP-branded item remains correctly excluded because
  its authoritative Search brand was blank.
