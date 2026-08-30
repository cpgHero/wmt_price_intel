# Phase 13.80 — Canonical Retailer Publication Scope

Date: 2026-08-30
Status: Implemented and release-tested; production deployment and blocked-job retry pending

## Outcome

Report publication now builds Price Intelligence catalog work from canonical governed retailer IDs rather than human-readable report labels. A label such as `ALDI` is presentation only; the deterministic Price Intelligence service is keyed by `aldi_us`.

## Incident and cause

The governed Banana composite analysis completed successfully, but its durable publication job blocked after three attempts while staging retailer catalogs. Production logs showed the exact failure:

`ValueError: retailer 'ALDI' is not in this analysis`

The publication planner had read `benchmark_retailer` and `competitors` from the rendered report view. Those fields intentionally contain display labels. The same view already exposes canonical IDs under `retailer_scope`, but the planner did not use them.

## Correction

- Read the benchmark and competitor service keys only from `retailer_scope`.
- Fail closed if the canonical benchmark, competitor list, or any canonical competitor ID is missing.
- When a governed report exposes `scoreable_retailers`, stage catalogs only for those competitors plus the benchmark.
- Reject a scoreable ID that is not present in the configured canonical competitor scope.
- Preserve display labels for presentation only.
- Preserve explicitly unavailable competitors in audit provenance without generating a misleading catalog or scorecard.

## Trust and compatibility

This change does not alter Search or PDP evidence, collection tasks, AI behavior, certification, Product Packs, prices, metrics, comparison relationships, geographic rules, or existing ready reports. The blocked successor remains inactive and the prior trusted Banana report remains current until a retried job passes the complete semantic publication gate.

## Verification

- Eight canonical-scope unit cases pass, including display-label separation, unavailable-retailer exclusion, missing-scope rejection, and unconfigured-scoreable rejection.
- Twenty-six focused API Price Intelligence, report-publication, and worker materialization tests pass.
- Production deployment, health checks, explicit job retry, full materialization, semantic audit, and predecessor archival remain required before this phase is production-complete.
