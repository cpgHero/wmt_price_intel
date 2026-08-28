# Phase 13.68 — Competitive Context-Switch Resilience

Date: 2026-08-27  
Status: Implemented; production verification pending

## Incident

Changing the Competitive Intelligence comparison basis could leave the active report at
`Building radius-native retailer scorecards…` with no completion, timeout, error, or recovery action.
The defect was most visible in Vitamins & Supplements because its compatible-specification portfolio
contains hundreds of certified relationship summaries and is materially larger than the other active
reports.

## Root cause

Phase 13.65 had limited radius-portfolio reads to the report tabs that consume them. A later
interaction change removed that demand guard so the complete portfolio was requested after every
report context change, including tabs with their own product-leadership read models. The same endpoint
also returned scorecard, cohort, assortment, product, and relationship-drawer evidence together. The
browser discarded the previous scorecard while the replacement document was transferred and parsed,
and the request had no client timeout or retry state.

The Phase 13.67 Price Intelligence catalog work did not change Competitive Intelligence formulas,
certified relationships, radius materializations, or report evidence. It did, however, share the same
release window in which the Competitive fetch guard was removed. Vitamins exposed the transport and
interaction defect because its compatible portfolio is the largest current Competitive document.

## Remediation

- Radius portfolios are requested only by Retailer Scorecards, Cohort Scorecards, and Assortment
  Scorecards.
- Each tab requests a projection containing only its visible evidence. The immutable stored portfolio
  remains complete and audit-ready.
- Retailer Scorecards receive aggregate scorecard rows without transferring product and relationship
  drawer payloads.
- Included-product evidence is loaded lazily for the selected competitor when the user opens its
  drawer.
- Context requests have a 20-second browser bound, a clear error, and an explicit Retry scorecards
  action instead of an indefinite building state.
- Changing basis, competitor, radius, state, or city continues to select the same pre-materialized
  governed result; the change affects transport and interaction only.

## Trust boundary

No Search, PDP, location, brand, seller, certification, Product Pack, comparison-basis, radius,
metric, denominator, price, report publication, or audit-lineage data changes. The full stored
portfolio remains the authority used by semantic release audits. Projections remove only evidence not
rendered by the active tab and never recompute analytical values in the browser.

## Verification requirements

- API projection unit tests prove the stored document is not mutated and inactive evidence is omitted.
- Web unit tests prove only the three consuming tabs request a portfolio and select the correct
  projection.
- Python lint/tests, TypeScript, ESLint, Prettier, web unit tests, and the production build must pass.
- Railway API and web deployments must become healthy.
- Live Vitamins acceptance must switch exact/compatible basis and 1/3/5-mile radius on Retailer
  Scorecards, open included-product evidence, traverse another Competitive tab, and confirm a clean
  browser console.
- A representative Price Intelligence catalog must still load after deployment.
