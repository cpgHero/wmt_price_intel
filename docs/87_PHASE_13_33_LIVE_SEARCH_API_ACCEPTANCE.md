# Phase 13.33 — Live Search API Acceptance

## Outcome

This phase validates the production MetricsCart Search-by-ZIP collection boundary with a deliberately
small, owner-approved, paid Strawberry study. It proves that the live provider payload—not a
historical CSV export—can pass cost approval, durable collection, immutable raw preservation,
versioned response auditing, normalization, analysis, and reporting without silent field loss or
schema drift.

The pilot passed. No adapter mapping or contract repair was required.

## Approved pilot scope

- Collection: `Fresh Strawberries Live API Acceptance 2026-08-21`
- Run ID: `4ac82ffa-7ec6-4175-86ed-6bc0ffbbb928`
- Definition version ID: `fd5ffa12-6a80-4d0b-ad42-48bc85bcc58d`
- Product Pack: Fresh Strawberries `1.0.1`
- Search term: `strawberries`
- Walmart: store `1539`, ZIP `44906`, Ontario, Ohio
- ALDI: store `463-048`, ZIP `44906`, Ontario, Ohio, within five miles of the benchmark store
- Amazon Same Day: benchmark ZIP service area `44906`
- Page depth: one page per retailer/location unit
- Hard cap: five Search credits
- PDP enrichment: disabled so Search acceptance could be evaluated independently
- Analysis ID: `fresh_strawberries-4ac82ffa-7ec6-4175-86ed-6bc0ffbbb928`
- Analysis-run ID: `76572052-cb2b-4442-a184-bf7c85945f8a`

## Live results and spend

| Retailer | HTTP | Credits | Result rows | Location authority |
|---|---:|---:|---:|---|
| Walmart | 200 | 1 | 44 | Task store `1539` and ZIP `44906` |
| ALDI | 200 | 2 | 15 | Payload and task agree on store `463-048` and ZIP `44906` |
| Amazon Same Day | 200 | 2 | 16 | ZIP-only task context `44906` |
| **Total** | **3 successful pages** | **5** | **75** | **No retries or 404s** |

At the owner-supplied rate of $0.002 per billable credit, the provider cost was approximately $0.01.
The ALDI availability gate passed and the collection completed in about 20 seconds. Analysis
completed on its first attempt.

## Contract and evidence audit

Every live payload exposed top-level `query` and `results` members. All result rows shared the same
31-field inventory pinned by the versioned Search contract. The audit confirmed:

- contract version `1.0.0` and result path `results` for all three pages;
- positive Search price as observed/in-stock authority;
- Search `is_sponsored` as sponsorship authority;
- task result counts equal raw result-array counts;
- stored response-audit documents equal independently rerun audits;
- compressed object checksums, decompressed body checksums, and byte sizes all reconcile;
- 75 normalized rows and 75 classified rows were retained;
- no null or nonpositive prices, missing retailer-product IDs, duplicate IDs within a page, missing
  product URLs, or missing primary images;
- the query echo uses provider names such as `page_number` and `retailer_store_id`; those diagnostic
  fields do not override the immutable collection-task context.

The immutable downstream evidence consists of three raw provider-response artifacts (11,717 bytes),
three normalized-offer artifacts (75 rows; 37,700 bytes), three classified-offer artifacts (75 rows;
45,933 bytes), and three match-detail artifacts (six rows; 22,477 bytes).

## Source-authority decisions

1. **Price and availability.** A numeric Search price greater than zero is the governed observed and
   in-stock rule. Provider `stock_availability` remains diagnostic only.
2. **Sponsorship.** Search `is_sponsored` is authoritative. The Walmart page identified four
   sponsored results; ALDI and Amazon identified none.
3. **Store and ZIP.** The durable task request is authoritative. Walmart returned null pickup fields,
   while ALDI echoed its store and ZIP and Amazon correctly remained ZIP-only.
4. **Seller and first-party status.** None of the three Search payloads contained seller. A retailer
   site identity such as `walmart.com` is not proof that an item is first-party. Walmart and Amazon
   marketplace governance must use PDP seller evidence when available; otherwise status remains
   explicitly seller-unknown and cannot be silently promoted to verified first party.
5. **Brand.** Brand was missing for every Walmart and Amazon result and for seven of 15 ALDI results.
   Search brand is therefore useful when supplied but cannot be the only brand-classification input.
   PDP evidence and the governed brand foundation remain required.
6. **Optional diagnostics.** Reviews, badges, and demand fields vary materially by retailer. They
   remain optional raw evidence until a named analytical use case defines a versioned canonical
   mapping. The full source row is retained in `NormalizedOffer.raw`.

## Reporting verdict

The smoke analysis completed and rendered. ALDI produced two certified relationships and two scored
product-locations in this deliberately tiny geography. Amazon produced no strict local relationship,
which is an honest sample limitation rather than a collection failure. The report is marked review
required and must not be confused with the trusted full-category Strawberry publication.

After acceptance, the blocked smoke AnalysisResult
`19f4d89d-c276-4a23-88f1-d28c0ce43ba2` was recoverably archived at
`2026-08-22T05:13:09.443789Z` so it does not appear in the active report list. Audit event
`analysis_result_archived_after_live_search_acceptance` records the exact reason and preserved
lineage. The collection run, definition, paid-call ledger, raw objects, normalized and classified
artifacts, analysis lineage, and audit events remain intact. Production reconciliation found exactly
five unarchived reports, one ready report for each certified release category.

## Release verification

Commit `4593859` records the acceptance contract and evidence. GitHub Actions run `32553613136`
passed formatting, lint, types, contracts, the complete Python and TypeScript suites, reversible
migrations, 14 browser tests, production builds, and all four service-container gates. Railway web
deployed the exact commit; API, worker, and scheduler remained on the latest code-affecting Search
contract commit because this final release changed documentation only. All Railway services,
Postgres, and the artifact bucket were online after archival.

## Next controlled rollout

Before a full-location collection, run a bounded multi-region acceptance using approximately five
Walmart benchmark stores across distinct regions, corresponding ALDI stores within the governed
radius, and the benchmark ZIP universe for Amazon Same Day. Keep one page per unit, preserve the
availability gate and hard credit cap, and audit regional location mapping, empty/404 behavior,
brand sparsity, seller/PDP coverage, and result-count distributions. PDP enrichment should remain a
separately estimated and approved stage.

No additional retailer may be enabled merely because it appears in the provider catalog. Each must
pass its own endpoint, parameter, location, billing, empty-page, response-shape, seller-governance,
and normalization preflight.
