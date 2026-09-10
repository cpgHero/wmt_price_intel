# Phase 13.90 — Price Architecture fail-closed preparation

## Status

Implemented, merged, deployed, and production-verified on 2026-09-10.

## Context

During the Fresh Shell Eggs materialization recovery, all Price Intelligence
catalogs and Competitive Portfolio documents eventually staged, but final
publication initially failed with `price_architecture_catalog_scope_mismatch`.

Inspection showed that a Price Architecture build had been created while API
and database connection pressure was present. The architecture path treated a
non-benchmark retailer preparation exception as an unavailable retailer, so a
partial matrix could be staged and rejected only at final publication.

## Decision

Price Architecture generation may represent a retailer as unavailable only when
its governed Search evidence is genuinely absent. Runtime or infrastructure
failures during retailer preparation must fail closed before matrix generation.

The architecture projector therefore refuses to build a partial matrix when
retailer preparation raises anything other than `LookupError`.

## Operational effect

- No Search collection is rerun.
- No provider, PDP, or AI call is made.
- No matching, price calculation, distribution rule, or report metric formula
  changes.
- Transient database, object-store, or runtime failures now fail the
  materialization stage instead of staging a misleading partial architecture
  matrix.
- Genuine missing competitor evidence can still be shown as an explicit
  unavailable retailer row.

## Verification

- Focused API tests cover both paths:
  - missing retailer evidence emits a zero-evidence unavailable row;
  - runtime preparation failure refuses to build a partial matrix.
- PR #4 passed release CI and merged as `a606748d`.
- Railway production health returned ready with API dependency OK.
- The deployed API container was inspected directly and contains the fail-closed
  preparation guard.
- Production report-library verification showed one active ready report and zero
  active blocked reports for Fresh Bananas, Fresh Fluid Milk, Fresh Ground Beef,
  Fresh Shell Eggs, and Fresh Strawberries.
