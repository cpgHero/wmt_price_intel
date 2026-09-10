# Phase 13.89 — Price catalog source-row authority

## Status

Implemented, merged, deployed, and production-verified on 2026-09-10.

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
- Publication remains fail-closed when catalog observation/source counts do not
  reconcile.

## Verification

- Focused API regression coverage passed locally.
- Release CI passed for PR #3.
- Railway production deployed the hotfix.
- The retained-evidence Fresh Shell Eggs replacement materialized successfully:
  14 Price Intelligence catalogs, 3 Price Architecture matrices, and 6
  Competitive Portfolio documents.
- The Egg publication job completed 24/24, final audit passed, and the active
  AnalysisResult is `reporting_status = ready`.
