# Phase 13.75 — Publication Lifecycle and Price Cold-Path Reliability

**Status:** deployed and production-attested on 2026-08-29
**Provider/AI spend:** zero
**Authoritative data or matching changes:** none

## Objective

Remove two operational defects identified by the Phase 13.74 recovery drill without changing Search evidence, PDP evidence, matching, prices, geography, Product Pack rules, or analytical calculations:

1. a successfully published replacement must recoverably retire an older blocked report for the same Product Pack; and
2. the default legacy Price Intelligence read must reuse the publication-bound compact catalog instead of rebuilding the complete classified Search population on a cold API process.

## Publication lifecycle correction

The publication gate previously archived only active predecessors whose reporting status was `ready`. A blocked Vitamin predecessor therefore remained active after its accepted Matching v2 successor became ready. The blocked row, validation history, materialization job, and audit lineage were intentionally preserved, but its active state caused System Operations to report stale publication attention.

After a replacement passes the semantic publication gate, activation now recoverably archives active same-Product-Pack predecessors whose status is either `ready` or `blocked`. Pending work is not retired. Archival sets `archived_at`; it does not delete or rewrite the predecessor, source data, PDP evidence, Matching v2 certification, validation issues, materialization job, or audit events. The successful publication audit continues to record the exact predecessor IDs retired during activation.

## Price cold-path correction

Publication already materializes a schema-valid compact Price Intelligence catalog for every configured retailer. The Home page uses its paged read, but the legacy unfiltered endpoint still rebuilt every retained classified Parquet artifact, product context, location population, and product projection. That duplicate cold path exceeded the recovery drill's 30-second operator window.

For an unfiltered default request only, the legacy endpoint now returns the stored publication-bound catalog when present. Product, state, city, ZIP, and brand-type filtered requests continue through the detailed evidence projection, so maps, product workspaces, and governed drill-down behavior are unchanged. Reports created before catalog materialization retain a compatibility fallback to the existing live projection.

## Trust and compatibility rules

- The shortcut never synthesizes, recalculates, or repairs price evidence.
- The stored catalog is generated and schema-validated during durable report materialization.
- A missing catalog falls back to the prior read path instead of making an older report unavailable.
- Filtered and product-level reads do not use the shortcut.
- Superseded blocked reports remain fully auditable and recoverable after archival.
- No provider, PDP, AI, collection, matching, or report-generation calls are introduced.

## Verification

- Targeted Price API tests prove the default request uses the stored catalog, filtered requests bypass the shortcut, and an absent catalog uses the compatibility fallback.
- The complete local suite passed with 793 Python tests and 85 web tests; Python/web formatting, lint, typing, production build, browser tests, migrations, contracts, documentation coverage, and all four container builds passed in GitHub Actions run `33281048900`.
- Railway API deployment `76510928-a410-4d39-8881-22002c7149f2` and web deployment `f5e12e6c-423a-4344-aa41-78e19bb29a91` succeeded on commit `81bccb4cd5f3c0d2c63dc70a6c246f9b3dbe8b6a`.
- The default 246-product Vitamin Price payload returned HTTP 200 in 0.91 seconds. A product-specific evidence read returned HTTP 200 in 5.49 seconds after object-storage credential rotation.
- The obsolete blocked Vitamin predecessor was recoverably archived at `2026-08-29T23:32:59Z`; an explicit audit event records the ready successor and release commit. Active blocked reports and active blocked materialization jobs both reconciled to zero, and System Operations returned `healthy`.

## Coordinated secret rotation

The release also rotated the app-owned API/worker internal service token, API/web administrator bridge token, and web session-signing secret. Existing administrator browser sessions were intentionally invalidated; the administrator password was not changed. Railway bucket S3 credentials were reset, synchronized to API and worker, and validated through a live product-specific evidence read. No secret value, credential payload, or reversible derivative is recorded in this phase document or Platform Docs.

OpenAI and MetricsCart API keys, the administrator password, and Postgres credentials were not silently replaced because their authoritative replacements require provider/operator coordination. PITR remains disabled pending a named stateful maintenance window.

## Follow-up boundary

Product-specific evidence already uses selective Parquet reads for requested product IDs. Broader redesign of geography projections or endpoint contracts is not required by this phase. PITR enablement and credential rotation remain separately coordinated maintenance work because they can redeploy stateful infrastructure or require new values from provider dashboards.
