# Phase 13.65 — Production Interaction Resilience

Date: 2026-08-27  
Status: Deployed and production-verified

## Incident

The production application returned healthy HTTP responses, but navigation and report controls could appear to do nothing during a client demonstration. This was a browser-interaction incident, not a database or API outage. Treating route health alone as release acceptance would have missed the failure.

## Root causes

1. Competitive Intelligence recalculated large report projections and cohort evidence whenever any tab state changed.
2. Decision-context arrays were recreated on every render and therefore recreated the application context definition. The context provider then scheduled another render, producing a client render loop on report interactions.
3. Price Intelligence transferred full PDP, distribution-gap, histogram, and sample-location evidence for every catalog product even though the Home list did not render those fields.
4. Price Intelligence constructed the entire retailer catalog and all interactive controls in the first browser render.
5. Same-origin route changes did not consistently show immediate navigation feedback.

## Remediation

- Memoized report scoping, decisions, map points, highlights, quality rows, relationship counts, and cohort evidence.
- Reused pre-materialized portfolio relationship summaries instead of rebuilding cohort product evidence in the browser.
- Removed tab state from the portfolio fetch key so identical evidence is not downloaded again when changing report tabs.
- Stabilized decision-context counts so the top application context no longer enters a render loop.
- Added a visible same-origin navigation indicator and a global Next.js loading boundary.
- Compacted catalog-only Price Intelligence responses. Full PDP and location evidence remains available when a user opens one product.
- Progressively renders 40 catalog products at a time, yields catalog expansion through a React transition, and applies browser layout containment to offscreen rows.

The largest current catalog response fell from 2,541,246 bytes to 747,734 bytes. Its server-rendered page fell from 3,307,221 bytes to 927,606 bytes. This optimization changes transfer and rendering only; it does not change Search evidence, PDP persistence, price metrics, or product counts.

## Production acceptance evidence

- Railway `web`, `api`, `worker`, `scheduler`, and Postgres instances were healthy; both `/health` and `/health/ready` returned HTTP 200.
- Home, Analyses, Price Intelligence, Collections, Data Quality, administrator Docs, Studies, and Match Certification returned HTTP 200.
- The largest Competitive Intelligence report loaded without console errors.
- All nine Competitive Intelligence tabs were clicked and selected successfully.
- Competitive View and Store Radius context drawers changed URL-backed scope correctly and closed after selection.
- The Retailer Scorecard included-products drawer opened with the expected retailer context.
- The largest Price Intelligence catalog hydrated with 40 initial products and no console errors; opening a product loaded its complete product workspace and visible loading state.
- Local gates passed TypeScript, ESLint, Prettier, 75 web tests, and the Next.js production build.

## Required post-change release gate

Every change affecting web routes, shared layout, application context, report workspaces, API proxy behavior, or production evidence materialization now requires all of the following before handoff:

1. CI success, including browser tests and production container builds.
2. Successful Railway deployment with a running healthy instance.
3. Live `/health` and `/health/ready` checks.
4. Direct live checks of the primary route library pages.
5. A live click-through of at least one largest representative Competitive Intelligence report and one largest Price Intelligence catalog.
6. Console-error inspection during the click-through.
7. Immediate rollback or continued remediation if a control does not visibly respond.

Build success alone is not production interaction acceptance.

## Governance

No collection, PDP, AI, certification, report evidence, or audit-lineage data changed. Catalog compaction is presentation transport only; product-detail requests retain full evidence.
