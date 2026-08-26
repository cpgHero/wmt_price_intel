# Phase 13.61 — Vitamin Reporting Acceptance and Coverage

Status: deployed, rematerialized, and production-verified

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

## Production acceptance

- Analysis: `vitamins_supplements-aee8a9d6-33e5-4bac-903c-2570d869db52-match-v2-71792d31`.
- Six Competitive Portfolio `1.4.0` documents were atomically rematerialized: Exact Specification and Compatible Specification at 1, 3, and 5 miles. The internal semantic release gate completed before storage and queued zero provider calls.
- The live Compatible Specification / 5-mile view accounts for 322 source products, 320 governed in scope, and 246 observed in-scope Walmart products for every competitor.
- The live Target ledger returns 322 rows and 322 unique product IDs: 39 locally scored, 207 without a certified Target relationship, 74 not observed in the retained Walmart Search evidence, and two governed exclusions. Its status partition equals the source catalog exactly.
- Compatible Specification / 5-mile scored product-locations are Target 39, Meijer 32, Amazon Same Day 31, Kroger 27, CVS 18, Sam's Club 16, BJ's 13, Walgreens 3, and Costco 1. Walgreens also exposes seven certified/eligible products without local competitor evidence instead of collapsing them into an unexplained zero.
- Exact Specification / 5-mile remains intentionally narrower: 39 scored product-locations across nine scorecards. Retailers with no exact-spec evidence remain explicit zeroes rather than borrowing compatible-spec evidence.
- The deployed report opens at Compatible Specification / 5 miles. All nine reporting workspaces render without load errors. The all-retailer Assortment state gives an explicit selection instruction; the Target-scoped view then renders its full scorecard with 246 Walmart products, 796 Target products, and 117 admitted compatible relationships.
- Railway deployments carrying the release: API `0fa0d4fe-c3ec-40f4-85de-0af73c8c5d2e`, web `7b41f5a3-4a0a-4313-94eb-ff88a54dc815`, worker `65569e67-6021-4df1-a1de-3c08b1c6a806`, and scheduler `1e22fafa-06a1-42b6-9c9e-665f626e1cd9`.

## Verification gates

- 773 Python tests pass; 16 environment- or fixture-dependent integration/golden tests skip with their documented prerequisites.
- 17 focused portfolio and semantic-release tests pass.
- 73 web unit tests pass.
- Web TypeScript and ESLint checks pass.
- Python Ruff format and lint checks pass.
- Mypy passes across 151 Python source files.
- Generated TypeScript contracts include Competitive Portfolio `1.4.0`, the coverage contract, and comparison-basis radius metadata.
- GitHub Actions run `33021321217` passes contracts, formatting, linting, type checking, migrations, the complete Python and TypeScript suites, production builds for all services, and all 15 Playwright browser tests.

No Search, PDP, MetricsCart, or AI call was made, and no certification decision, immutable source, or historical report was deleted or rewritten.
