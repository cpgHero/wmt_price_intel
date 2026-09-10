# Phase 13.89 — Price catalog source-row authority

## Status

Implemented and syntax-verified on 2026-09-10. Release CI, Railway deployment,
Egg materialization retry, and production acceptance remain pending.

## Context

The retained-evidence Egg replacement reached final report publication, but the
publication trust gate blocked activation with
`price_catalog_observation_counts_invalid`.

Production inspection showed that each non-Walmart Egg Price Intelligence
catalog had valid positive Search observations and classified rows, but reported
`source.source_rows = 0`. Walmart reported a populated source-row count. The
trust gate was right to block this because a catalog cannot honestly claim
thousands of classified positive-price observations from zero source rows.

## Decision

Price Intelligence catalog `source_rows` must be derived from the selected
immutable classified Search artifacts used by the projection.

Those artifacts are already selected through the AnalysisResult evidence
manifest, including row-count and checksum reconciliation. The selected artifact
row-count sum is therefore the authoritative catalog source population for the
published document.

## Operational effect

- No Search collection is rerun.
- No provider, PDP, or AI call is made.
- No match decision, price calculation, distribution rule, or report metric
  formula changes.
- Publication remains fail-closed until the corrected projection is deployed and
  the blocked Egg materialization job is retried successfully.

## Verification

- Syntax verification passed for the changed API source and focused API test
  file.
- The focused pytest invocation did not complete collection in the local harness
  and was interrupted after it hung during import. Release CI must be used as the
  authoritative pre-deployment test gate.
