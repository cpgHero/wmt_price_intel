# Phase 13.67 — Durable Price Intelligence Catalogs

Date: 2026-08-27  
Status: Implemented; production verification pending

## Outcome

Price Intelligence Home no longer requires a cold, request-time reconstruction of every product,
location, and PDP evidence object. The governed report-publication job now builds one compact product
catalog for every configured retailer from retained Search, location-master, PDP, brand, Product Pack,
and seller-governance evidence. Catalogs are staged beside the existing price-architecture and
competitive-portfolio read models and become visible only in the same atomic publication transaction.

The browser receives 40 product rows at a time. Search, brand, brand type, seller, and pagination are
applied by the API against the immutable materialized catalog. Opening a product still requests the
complete product workspace with its location, price-distribution, map, PDP, and supporting evidence.
No analytical metric, source authority, first-party policy, Product Pack rule, match decision, or
reporting denominator changes in this phase.

## Durable publication flow

1. The publication planner derives the exact configured retailer set from the pending AnalysisResult.
2. The leased worker builds one retailer catalog at a time so publication cannot impair interactive
   API readiness.
3. Each catalog is validated against the normative Price Monitoring view contract and staged with a
   deterministic checksum.
4. The publication gate blocks activation when any configured retailer catalog is absent.
5. One transaction installs catalogs, price-architecture matrices, competitive portfolios, and the
   semantic audit before activating the replacement report and recoverably archiving predecessors.
6. A retry resumes already staged catalogs and never recollects Search/PDP data or invokes AI.

## Read behavior

- `GET /api/v1/analyses/{analysis_id}/price-monitoring/catalog` reads only an active, unarchived,
  materialized catalog.
- The endpoint supports `retailer`, `q`, `brand_type`, `brand`, `seller`, `offset`, and `limit`; the
  limit is bounded to 100.
- Results are ordered by distinct observed retailer locations descending, then product name and ID.
- The response includes complete facet values and total/filtered/returned counts.
- Geography-scoped catalog variants remain on the existing deterministic read path. Product detail is
  always lazy and retains the complete evidence model.
- An authenticated internal endpoint supports zero-provider-call catalog backfill for already active
  reports.

## Database and rollback

Migration `0048_price_catalog` adds `price_monitoring_catalog_materialization`, uniquely scoped by
AnalysisResult and retailer, and extends the existing staging-kind constraint with `price_catalog`.
The downgrade removes only derived catalog documents and restores the prior staging constraint. Raw
objects, normalized Search, PDP snapshots, certifications, AnalysisResults, publications, and audit
lineage are unaffected.

## Verification gates

- reversible Alembic head;
- focused API catalog filtering/sorting/pagination tests;
- report-worker resume and bounded catalog execution tests;
- Python lint and focused tests;
- web lint, typecheck, unit tests, and production build;
- live API readiness during backfill;
- live Home initial response size/time, filter, load-more, product-open, and console verification.

The production status in this record and Platform Docs must be updated only after deployment,
backfill, and browser verification complete.
