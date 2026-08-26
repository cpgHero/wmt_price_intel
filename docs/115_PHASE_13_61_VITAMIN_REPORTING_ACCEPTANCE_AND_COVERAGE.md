# Phase 13.61 — Vitamin Reporting Acceptance and Coverage

Status: implemented and locally trust-gated; production deployment and live acceptance pending

Date: 2026-08-26

## Objective

Make every Spring Valley reporting denominator inspectable from the complete governed Walmart catalog through final local price scoring, then validate that all Competitive Intelligence workspaces consume the same certified relationship, price-basis, and geography rules.

This phase does not collect Search or PDP data, call an AI model, alter a certification decision, or archive a report.

## Authoritative grains

- Catalog coverage: one governed Walmart catalog product × competitor retailer × selected comparison basis × radius.
- Certified identity: one immutable certified Walmart-product/competitor-product relationship, independent of price availability.
- Price-basis eligibility: a certified relationship with the deterministic package or normalized-unit evidence required by the selected Product Pack profile.
- Local score: one observed Walmart product-store with the lowest eligible competitor offer inside the selected 1-, 3-, or 5-mile radius. Service-area retailers retain the explicitly labeled same-delivery-ZIP exception.
- Search is authoritative for price, positive-price observation, sponsorship, seller evidence when supplied, and store/location occurrence. PDP evidence supports identity, attributes, images, package/serving denominators, and seller enrichment; it does not replace Search price.

## Complete benchmark denominator

The Vitamin Product Pack contains 322 source Walmart Spring Valley product IDs. Of these, 320 are governed in scope and two (`631199053` and `240505739`) are explicitly excluded topical skin oils. The ledger still displays all 322 so an exclusion is visible rather than silently lost. A Search non-observation remains an evidence gap, not proof that a product is discontinued or unavailable nationally.

For Product Packs without an explicit catalog, the generic engine uses the union of admitted observed and certified benchmark products. There is no vitamin-specific branch in the core engine.

## Mutually exclusive product dispositions

Every source catalog product appears exactly once for each competitor:

1. `governed_out_of_scope` — the product is intentionally excluded by the Product Pack.
2. `benchmark_not_observed` — no positive-price Walmart Search observation is retained.
3. `no_certified_relationship` — observed at Walmart, but no certified relationship exists for this competitor.
4. `no_selected_price_basis` — certified identity exists, but not under the selected package/unit price basis.
5. `no_local_competitor_evidence` — selected-basis relationship exists, but no locally scorable competitor evidence is available in the selected radius.
6. `scored` — at least one governed Walmart product-location has a local eligible comparison.

These statuses partition the complete catalog exactly. Their sum must equal the catalog denominator.

## Contract and publication changes

- Competitive Portfolio schema `1.4.0` adds an `evidence_funnel` to each retailer scorecard.
- A separate `competitive-product-coverage` contract returns the complete per-product ledger on demand, avoiding multi-thousand-row duplication across all six pre-materialized portfolio documents.
- The report-view comparison-basis contract now carries the Product Pack's configured `radius_miles` when geography is radius-based.
- The browser uses that configured radius as its initial state instead of hard-coding three miles. User-selected 1-, 3-, and 5-mile views remain available and URL-addressable.
- Retailer Scorecards can open the complete catalog lineage, filter by disposition, search by product name/ID, and download the full ledger as CSV.

## Automatic publication gates

Schema `1.4.0` materialization fails before publication when:

- the funnel is absent;
- the governed in-scope catalog exceeds the source catalog;
- observed products exceed the governed in-scope catalog;
- selected-basis products exceed certified identity products;
- locally scored products exceed observed or selected-basis products;
- funnel scored product-locations differ from the scorecard;
- the six product dispositions do not partition the complete 322-product source catalog exactly;
- catalog, observation, certification, or selected-basis counts drift when only radius changes; or
- locally scored product counts decrease as the physical-store radius widens.

Existing product, relationship, cohort, assortment, rate, weighted-gap, ordering, and 1/3/5-mile monotonicity gates remain active.

## Workspace acceptance matrix

| Workspace | Authoritative input | Acceptance requirement |
| --- | --- | --- |
| Retailer Scorecards | Portfolio scorecard + coverage ledger | Counts reconcile from certified identity through scored product-locations; complete catalog drill-down is available. |
| Cohort Scorecards | Radius-native cohort relationship lineage | Cohort counts and outcomes equal included relationship rows; incomplete attributes remain explicit gaps. |
| Competitive Footprint | Product-location outcomes | Individual benchmark and competitor stores use the selected radius; service areas are labeled separately. |
| Matched Price Matrix | Certified relationship outcomes | Each cell retains product and local evidence lineage under the selected basis/radius. |
| Match Summary | Certified relationship ledger | Approved products are ordered by observed/scored evidence and never imply price coverage where none exists. |
| Price Ladders | Footprint-level governed outcomes | Rungs summarize the selected product's observed footprint, not one arbitrary store; Walmart remains highlighted. |
| Store Comparisons | Product-location outcomes | Details and exception toggle share the same radius-native evidence and exports. |
| Assortment Scorecards | Observed assortment + certified identities + portfolio outcome | Identity/whitespace and local price coverage remain distinct and drillable. |
| Competitive History | Compatible dated publications | Remains non-decisional until at least two certified comparable snapshots exist. |

## Local verification

- 51 targeted Python contract, service, and semantic-release tests pass.
- 73 web unit tests pass.
- Web TypeScript and ESLint checks pass.
- Python Ruff format and lint checks pass.
- Generated TypeScript contracts include Competitive Portfolio `1.4.0`, the coverage contract, and comparison-basis radius metadata.

Production IDs, exact live funnel counts, browser acceptance, CI run, and Railway deployment identifiers will be appended only after those checks complete.
